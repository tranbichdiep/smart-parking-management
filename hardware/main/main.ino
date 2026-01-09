/**
 * Project: RFID Servo Control - Smart Parking System
 * Upgrade: WiFiManager & Configurable Server IP
 */

#include <SPI.h>
#include <MFRC522.h>
#include <ESP32Servo.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <WiFiManager.h> // Cần cài thư viện WiFiManager by tzapu
#include <Preferences.h> // Thư viện lưu trữ vào Flash (có sẵn trong ESP32 Core)

// --- CẤU HÌNH MẶC ĐỊNH ---
// Các giá trị này sẽ hiển thị gợi ý trong trang cấu hình
char server_ip[40] = "192.168.0.101"; 
char server_port[6] = "5000";
char device_token[40] = "my_secret_device_token_12345";

// --- KHỞI TẠO CÁC ĐỐI TƯỢNG ---
Preferences preferences; // Để lưu IP Server vào bộ nhớ máy
WiFiManager wm;          // Quản lý kết nối WiFi

// --- API Endpoints ---
const char* API_DEVICE_SCAN = "/api/gate/device_scan";
const char* API_CHECK_STATUS = "/api/gate/check_action_status";

// --- RFID pins ---
#define SS_PIN  5
#define RST_PIN 22
MFRC522 mfrc522(SS_PIN, RST_PIN);

// --- SERVO ---
#define SERVO_PIN 27
Servo myServo;

// --- SENSOR ---
#define SENSOR_PIN 26

// --- NÚT RESET CONFIG (Dùng nút BOOT trên mạch ESP32 - GPIO 0) ---
#define TRIGGER_PIN 0 

// --- Biến quản lý trạng thái cổng ---
int gatePhase = 0;

// --- Cooldown & Polling ---
unsigned long lastTriggerTime = 0;
const unsigned long COOL_DOWN_MS = 3000UL;

enum State {
  STATE_IDLE,    
  STATE_POLLING   
};
State currentState = STATE_IDLE;
unsigned long pollingStartTime = 0; 
unsigned long lastPollCheck = 0;    
int currentPollId = 0;
const unsigned long POLLING_TIMEOUT = 30000UL; 
const unsigned long POLLING_INTERVAL = 1000UL; 

// Flag để lưu config khi người dùng ấn Save trên Portal
bool shouldSaveConfig = false;

// Callback khi WiFiManager lưu cấu hình
void saveConfigCallback () {
  Serial.println("Should save config");
  shouldSaveConfig = true;
}

// --- Prototypes ---
String getCardUID(MFRC522::Uid uid);
void triggerOpen();
void handleIdleState();    
void handlePollingState(); 
void startPolling(int pollId);
void stopPolling();

void setup() {
  Serial.begin(115200);
  Serial.println("\n[Project] Smart Parking - WiFiManager Version");

  // 1. Cấu hình chân
  pinMode(SENSOR_PIN, INPUT);
  pinMode(TRIGGER_PIN, INPUT_PULLUP); // Nút BOOT

  // 2. Khởi tạo thiết bị ngoại vi
  SPI.begin(18, 19, 23, SS_PIN);
  mfrc522.PCD_Init();
  myServo.attach(SERVO_PIN);
  myServo.write(0); // Đóng cổng

  // 3. Load cấu hình cũ từ bộ nhớ Flash
  // --- SỬA ĐỔI: Mở -> Đọc -> Đóng ngay lập tức ---
  preferences.begin("parking_config", false); 
  
  if (preferences.isKey("server_ip")) { 
    // Kiểm tra xem đã có key chưa để tránh lỗi null
    String load_ip = preferences.getString("server_ip", "192.168.0.101");
    String load_port = preferences.getString("server_port", "5000");
    String load_token = preferences.getString("device_token", "my_secret_device_token_12345");
  
    load_ip.toCharArray(server_ip, 40);
    load_port.toCharArray(server_port, 6);
    load_token.toCharArray(device_token, 40);
  }
  
  Serial.println("--- Current Config ---");
  Serial.printf("Server IP: %s\n", server_ip);
  Serial.printf("Port: %s\n", server_port);
  Serial.println("----------------------");
  
  preferences.end(); // <--- QUAN TRỌNG: Đóng lại ngay sau khi đọc
  // ----------------------------------------------

  // 4. Cấu hình WiFiManager
  wm.setSaveConfigCallback(saveConfigCallback);
  // Tùy chọn: Tự thoát Portal nếu lưu thành công kể cả khi WiFi chưa kết nối ngay
  wm.setBreakAfterConfig(true); 

  WiFiManagerParameter custom_server_ip("server_ip", "IP May Chu", server_ip, 40);
  WiFiManagerParameter custom_server_port("server_port", "Port", server_port, 6);
  WiFiManagerParameter custom_device_token("device_token", "Device Token", device_token, 40);

  wm.addParameter(&custom_server_ip);
  wm.addParameter(&custom_server_port);
  wm.addParameter(&custom_device_token);

  // LOGIC RESET CẤU HÌNH
  if (digitalRead(TRIGGER_PIN) == LOW) {
    Serial.println("Nut BOOT duoc nhan! Dang reset WiFi settings...");
    wm.resetSettings();
    // Xóa cả cấu hình trong Preferences nếu muốn reset triệt để
    preferences.begin("parking_config", false);
    preferences.clear();
    preferences.end();
    delay(1000);
  }

  // Kết nối WiFi
  if (!wm.autoConnect("Diep_ESP32")) {
    Serial.println("Ket noi that bai hoac timeout. Resetting...");
    ESP.restart();
  }

  Serial.println("Da ket noi WiFi!");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());

  // 5. Lưu lại cấu hình mới nếu người dùng vừa nhập thay đổi
  if (shouldSaveConfig) {
    // Lấy giá trị từ WiFiManager
    strcpy(server_ip, custom_server_ip.getValue());
    strcpy(server_port, custom_server_port.getValue());
    strcpy(device_token, custom_device_token.getValue());

    Serial.println("Dang luu cau hinh moi vao Flash...");
    
    // --- SỬA ĐỔI: Mở lại Preferences chỉ để Ghi ---
    preferences.begin("parking_config", false); 
    preferences.putString("server_ip", server_ip);
    preferences.putString("server_port", server_port);
    preferences.putString("device_token", device_token);
    preferences.end(); // Đóng lại ngay sau khi ghi
    // ---------------------------------------------
    
    Serial.println("Luu thanh cong!");
  }
}

void loop() {
  // Logic cổng thông minh (Xe qua mới đóng)
  if (gatePhase == 1) {
    if (digitalRead(SENSOR_PIN) == LOW) { // Có xe che
      Serial.println("Xe bat dau di qua...");
      gatePhase = 2; 
    }
  }
  else if (gatePhase == 2) {
    if (digitalRead(SENSOR_PIN) == HIGH) { // Xe đi hết
      Serial.println("Xe da qua hoan toan. Dong cong!");
      delay(1000);
      myServo.write(0); 
      gatePhase = 0;
    }
  }

  // State Machine xử lý thẻ
  switch (currentState) {
    case STATE_IDLE:
      handleIdleState();
      break;
    case STATE_POLLING:
      handlePollingState();
      break;
  }
  
  delay(10);
}

// --- CÁC HÀM XỬ LÝ ---

void handleIdleState() {
  if (!mfrc522.PICC_IsNewCardPresent()) return;
  if (!mfrc522.PICC_ReadCardSerial()) return;

  unsigned long now = millis();
  if (now - lastTriggerTime < COOL_DOWN_MS) {
    mfrc522.PICC_HaltA(); 
    return;
  }

  // Kiểm tra WiFi trước khi gửi
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Mat WiFi! Dang thu ket noi lai...");
    // WiFiManager tự xử lý reconnect, ta chỉ cần đợi
    return; 
  }

  String cardUid = getCardUID(mfrc522.uid);
  Serial.printf("Quet the: %s\n", cardUid.c_str());

  HTTPClient http;
  char serverUrl[128];
  // SỬ DỤNG IP VÀ PORT TỪ BIẾN CẤU HÌNH
  sprintf(serverUrl, "http://%s:%s%s", server_ip, server_port, API_DEVICE_SCAN);
  
  Serial.printf("Goi API: %s\n", serverUrl);

  http.begin(serverUrl);
  http.addHeader("Content-Type", "application/json");

  StaticJsonDocument<200> jsonDoc;
  jsonDoc["card_id"] = cardUid;
  jsonDoc["token"] = device_token;
  String jsonPayload;
  serializeJson(jsonDoc, jsonPayload);

  int httpResponseCode = http.POST(jsonPayload);
  if (httpResponseCode > 0) {
    String responsePayload = http.getString();
    Serial.printf("Server tra ve: %s\n", responsePayload.c_str());
    StaticJsonDocument<256> responseDoc;
    deserializeJson(responseDoc, responsePayload);
    
    const char* action = responseDoc["action"];
    
    if (action && strcmp(action, "open") == 0) {
      Serial.println("Mo cong tu dong");
      triggerOpen();
      lastTriggerTime = millis();
    } 
    else if (action && strcmp(action, "poll") == 0) {
      int pollId = responseDoc["poll_id"];
      startPolling(pollId); 
    }
    else {
      Serial.println("Server tu choi."); // wait
      lastTriggerTime = millis();
    }
  } else {
    Serial.printf("Loi HTTP POST: %s\n", http.errorToString(httpResponseCode).c_str());
    lastTriggerTime = millis(); 
  }
  http.end();
  mfrc522.PICC_HaltA();
}

void handlePollingState() {
  unsigned long now = millis();
  if (now - pollingStartTime > POLLING_TIMEOUT) {
    Serial.println("\nQua thoi gian cho duyet.");
    stopPolling();
    return;
  }
  if (now - lastPollCheck < POLLING_INTERVAL) return;

  lastPollCheck = now;
  
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient httpPoll;
  char pollUrl[128];
  // SỬ DỤNG IP VÀ PORT TỪ BIẾN CẤU HÌNH
  sprintf(pollUrl, "http://%s:%s%s?id=%d", server_ip, server_port, API_CHECK_STATUS, currentPollId);
  
  httpPoll.begin(pollUrl);
  int httpResponseCode = httpPoll.GET();

  if (httpResponseCode > 0) {
    String responsePayload = httpPoll.getString();
    StaticJsonDocument<128> statusDoc;
    deserializeJson(statusDoc, responsePayload);
    const char* status = statusDoc["status"];

    if (status && strcmp(status, "approved") == 0) {
      Serial.println("\nBaove da duyet! Mo cong.");
      triggerOpen(); 
      stopPolling();
    }
    else if (status && strcmp(status, "denied") == 0) {
      Serial.println("\nBaove Tu choi.");
      stopPolling();
    }
  } 
  httpPoll.end();
}

void startPolling(int pollId) {
  Serial.printf("Cho bao ve xac nhan (ID: %d)...\n", pollId);
  currentState = STATE_POLLING;
  currentPollId = pollId;
  pollingStartTime = millis();
  lastPollCheck = millis();
}

void stopPolling() {
  currentState = STATE_IDLE;
  currentPollId = 0;
  lastTriggerTime = millis();
  Serial.println("Trang thai IDLE.");
}

String getCardUID(MFRC522::Uid uid) {
  String uidString = "";
  for (byte i = 0; i < uid.size; i++) {
    char hex[4];
    sprintf(hex, "%02X", uid.uidByte[i]);
    uidString += String(hex);
    if (i < uid.size - 1) uidString += " ";
  }
  return uidString;
}

void triggerOpen() {
  myServo.write(90);
  gatePhase = 1; // Chờ xe vào
  Serial.println("Servo MO. Cho xe di qua (Block -> Clear)...");
}