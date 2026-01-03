/**
 * Project: RFID Servo Control - Event Based Closing
 * * Mô tả:
 * - Hệ thống sử dụng cơ chế "Xe qua mới đóng" (Pass-through logic).
 * - Quy trình: Mở -> Chờ che cảm biến -> Chờ hết che -> Đóng.
 * - KHÔNG sử dụng hẹn giờ tự đóng.
 */

#include <SPI.h>
#include <MFRC522.h>
#include <ESP32Servo.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ================== CẤU HÌNH CẦN THAY ĐỔI ==================
const char* WIFI_SSID = "nosiaht_esp";    // <-- THAY TÊN WIFI
const char* WIFI_PASS = "88888888"; // <-- THAY PASS WIFI
const char* SERVER_IP = "192.168.0.101"; // <-- THAY IP SERVER
const int SERVER_PORT = 5000;
const char* DEVICE_TOKEN = "my_secret_device_token_12345";
// ===========================================================

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

// --- SENSOR (CẢM BIẾN VẬT CẢN) ---
#define SENSOR_PIN 26
// Mặc định cảm biến IR: LOW = Có vật cản, HIGH = Không có vật cản

// --- Biến quản lý trạng thái đóng mở cổng ---
// 0: Cổng đóng/Idle
// 1: Cổng mở, đang chờ xe đi vào (Chờ che cảm biến)
// 2: Xe đang ở giữa cổng, chờ xe đi ra (Chờ hết che cảm biến)
int gatePhase = 0; 

// --- Cooldown (tránh quét 2 lần) ---
unsigned long lastTriggerTime = 0;
const unsigned long COOL_DOWN_MS = 3000UL;

// --- State Machine (Máy trạng thái RFID) ---
enum State {
  STATE_IDLE,     // Chờ quét
  STATE_POLLING   // Đang chờ duyệt
};
State currentState = STATE_IDLE;
unsigned long pollingStartTime = 0; 
unsigned long lastPollCheck = 0;    
int currentPollId = 0;              

const unsigned long POLLING_TIMEOUT = 30000UL; 
const unsigned long POLLING_INTERVAL = 1000UL; 

// --- Prototypes ---
String getCardUID(MFRC522::Uid uid);
void triggerOpen(); 
void connectWiFi(unsigned long timeout_ms = 15000UL);
void maintainWiFi();
void handleIdleState();    
void handlePollingState(); 
void startPolling(int pollId);
void stopPolling();

void setup() {
  Serial.begin(115200);
  Serial.println("\n[Project] RFID Parking - Pass-through Logic");
  Serial.println("System initializing...");
  
  // 1. Cấu hình cảm biến
  pinMode(SENSOR_PIN, INPUT); // Cần thiết lập INPUT

  connectWiFi();
  SPI.begin(18, 19, 23, SS_PIN);
  mfrc522.PCD_Init();
  myServo.attach(SERVO_PIN);
  myServo.write(0); // Đóng ban đầu
  Serial.println("System ready.");
}

/**
 * Hàm loop chính (Non-Blocking)
 */
void loop() {
  // ============================================================
  // 0. LOGIC ĐÓNG CỔNG THEO SỰ KIỆN (XE QUA MỚI ĐÓNG)
  // ============================================================
  
  if (gatePhase == 1) {
    // [GIAI ĐOẠN 1]: Cổng đang mở, chờ xe bắt đầu đi qua
    // Kiểm tra xem cảm biến có bị che không (LOW)
    if (digitalRead(SENSOR_PIN) == LOW) {
      Serial.println("Vehicle started passing (Sensor blocked)...");
      gatePhase = 2; // Chuyển sang giai đoạn chờ xe đi hết
    }
  }
  else if (gatePhase == 2) {
    // [GIAI ĐOẠN 2]: Xe đang chắn, chờ xe đi hết
    // Kiểm tra xem cảm biến đã thoáng chưa (HIGH)
    if (digitalRead(SENSOR_PIN) == HIGH) {
      Serial.println("Vehicle passed completely. Closing gate!");
      delay(1000);
      myServo.write(0); // Đóng ngay lập tức
      gatePhase = 0;    // Reset về trạng thái đóng
    }
  }
  // Nếu gatePhase == 0 thì không làm gì cả (Servo giữ nguyên 0)

  // ============================================================

  // 1. Duy trì WiFi
  maintainWiFi();

  // 2. Chạy State Machine (Xử lý thẻ)
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


// ================= CÁC HÀM XỬ LÝ (GIỮ NGUYÊN) =================

void handleIdleState() {
  if (!mfrc522.PICC_IsNewCardPresent()) return;
  if (!mfrc522.PICC_ReadCardSerial()) return;
  
  unsigned long now = millis();
  if (now - lastTriggerTime < COOL_DOWN_MS) {
    Serial.println("Cooldown... Skipping.");
    mfrc522.PICC_HaltA(); 
    return;
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Error: WiFi disconnected.");
    mfrc522.PICC_HaltA();
    return;
  }

  String cardUid = getCardUID(mfrc522.uid);
  Serial.printf("Card scanned: %s\n", cardUid.c_str());

  HTTPClient http;
  char serverUrl[100];
  sprintf(serverUrl, "http://%s:%d%s", SERVER_IP, SERVER_PORT, API_DEVICE_SCAN);
  
  http.begin(serverUrl);
  http.addHeader("Content-Type", "application/json");

  StaticJsonDocument<128> jsonDoc;
  jsonDoc["card_id"] = cardUid;
  jsonDoc["token"] = DEVICE_TOKEN;
  String jsonPayload;
  serializeJson(jsonDoc, jsonPayload);

  Serial.println("Sending request...");
  int httpResponseCode = http.POST(jsonPayload);
  
  if (httpResponseCode > 0) {
    String responsePayload = http.getString();
    Serial.printf("Server: %s\n", responsePayload.c_str());
    StaticJsonDocument<256> responseDoc;
    deserializeJson(responseDoc, responsePayload);
    const char* action = responseDoc["action"];
    
    if (action && strcmp(action, "open") == 0) {
      Serial.println("Opening gate (Automatic)");
      triggerOpen();
      lastTriggerTime = millis();
    } 
    else if (action && strcmp(action, "poll") == 0) {
      int pollId = responseDoc["poll_id"];
      startPolling(pollId); 
    }
    else {
      Serial.println("Server denied access.");
      lastTriggerTime = millis(); 
    }
  } else {
    Serial.printf("HTTP POST Error: %s\n", http.errorToString(httpResponseCode).c_str());
    lastTriggerTime = millis(); 
  }
  http.end();
  mfrc522.PICC_HaltA();
}

void handlePollingState() {
  unsigned long now = millis();
  if (now - pollingStartTime > POLLING_TIMEOUT) {
    Serial.println("\nPolling timeout.");
    stopPolling();
    return;
  }
  if (now - lastPollCheck < POLLING_INTERVAL) return;

  lastPollCheck = now;
  Serial.print(".");

  if (WiFi.status() != WL_CONNECTED) {
     stopPolling();
     return;
  }

  HTTPClient httpPoll;
  char pollUrl[100];
  sprintf(pollUrl, "http://%s:%d%s?id=%d", SERVER_IP, SERVER_PORT, API_CHECK_STATUS, currentPollId);
  httpPoll.begin(pollUrl);
  int httpResponseCode = httpPoll.GET();
  
  if (httpResponseCode > 0) {
    String responsePayload = httpPoll.getString();
    StaticJsonDocument<128> statusDoc;
    deserializeJson(statusDoc, responsePayload);
    const char* status = statusDoc["status"];

    if (status && strcmp(status, "approved") == 0) {
      Serial.println("\nApproved! Opening gate.");
      triggerOpen(); 
      stopPolling();
    }
    else if (status && strcmp(status, "denied") == 0) {
      Serial.println("\nAccess denied.");
      stopPolling();
    }
  } 
  httpPoll.end();
}

void startPolling(int pollId) {
  Serial.printf("Waiting for approval (ID: %d)...\n", pollId);
  currentState = STATE_POLLING;
  currentPollId = pollId;
  pollingStartTime = millis();
  lastPollCheck = millis();
}

void stopPolling() {
  currentState = STATE_IDLE;
  currentPollId = 0;
  lastTriggerTime = millis();
  Serial.println("Waiting for card removal...");
  while(mfrc522.PICC_IsNewCardPresent()) { delay(50); }
  Serial.println("Ready.");
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

/**
 * @brief Kích hoạt servo mở
 * ĐÃ SỬA: Không dùng hẹn giờ. Chỉ mở và đặt trạng thái chờ xe.
 */
void triggerOpen() {
  myServo.write(90);

  // Kích hoạt Phase 1: Chờ xe vào che cảm biến
  gatePhase = 1;

  Serial.println("Servo opened. Waiting for vehicle to pass (Block -> Clear)...");
}

void connectWiFi(unsigned long timeout_ms) {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.printf("Connecting to WiFi \"%s\"...\n", WIFI_SSID);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - start) < timeout_ms) {
    delay(250); Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("IP: "); Serial.println(WiFi.localIP());
  } else {
    Serial.println("WiFi Error.");
  }
}

void maintainWiFi() {
  static unsigned long lastCheck = 0;
  if (millis() - lastCheck >= 10000UL) {
    lastCheck = millis();
    if (WiFi.status() != WL_CONNECTED) connectWiFi(7000UL);
  }
}