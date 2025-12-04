/**
 * Project: RFID Servo Control with HTTP Polling (Non-Blocking)
 * * Mô tả:
 * Sử dụng State Machine (máy trạng thái) để không bao giờ "chặn" (block) hàm loop().
 * Điều này giúp sửa lỗi ESP32 bị crash/reset.
 * * * Trạng thái:
 * 1. IDLE: Chờ quét thẻ.
 * 2. POLLING: Đang chờ bảo vệ duyệt (gửi HTTP GET mỗi giây).
 * * * Yêu cầu Thư viện (Arduino Library Manager):
 * 1. MFRC522
 * 2. ESP32Servo
 * 3. ArduinoJson
 */

#include <SPI.h>
#include <MFRC522.h>
#include <ESP32Servo.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ================== CẤU HÌNH CẦN THAY ĐỔI ==================
const char* WIFI_SSID = "nosiaht";    // <-- THAY TÊN WIFI CỦA BẠN
const char* WIFI_PASS = "88888888"; // <-- THAY MẬT KHẨU WIFI
const char* SERVER_IP = "192.168.0.100"; // <-- THAY IP SERVER (IP máy chạy app.py)
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
const unsigned long OPEN_TIME_MS = 3000UL;
unsigned long servoCloseTime = 0; // (ĐÃ SỬA) Biến hẹn giờ đóng Servo

// --- Cooldown (tránh quét 2 lần) ---
unsigned long lastTriggerTime = 0;
const unsigned long COOL_DOWN_MS = 3000UL; // Tăng lên 3s

// --- State Machine (Máy trạng thái) ---
enum State {
  STATE_IDLE,     // Chờ quét
  STATE_POLLING   // Đang chờ duyệt
};
State currentState = STATE_IDLE;
unsigned long pollingStartTime = 0; // Mốc thời gian bắt đầu chờ
unsigned long lastPollCheck = 0;    // Mốc thời gian hỏi server lần cuối
int currentPollId = 0;              // ID của yêu cầu đang chờ

const unsigned long POLLING_TIMEOUT = 30000UL; // Chờ tối đa 30 giây
const unsigned long POLLING_INTERVAL = 1000UL; // Hỏi server mỗi 1 giây


// --- Khai báo hàm (Prototypes) ---
String getCardUID(MFRC522::Uid uid);
void triggerOpen(); // (ĐÃ SỬA)
void connectWiFi(unsigned long timeout_ms = 15000UL);
void maintainWiFi();
void handleIdleState();    // Hàm xử lý khi đang chờ
void handlePollingState(); // Hàm xử lý khi đang chờ duyệt
void startPolling(int pollId);
void stopPolling();

void setup() {
  Serial.begin(115200);
  Serial.println("\n[Project] RFID HTTP Polling Client (Non-Blocking)");
  connectWiFi();
  SPI.begin(18, 19, 23, SS_PIN);
  mfrc522.PCD_Init();
  myServo.attach(SERVO_PIN);
  myServo.write(0);
  Serial.println("Hệ thống sẵn sàng.");
}

/**
 * @brief (ĐÃ SỬA LỖI BLOCKING) Hàm loop() chính.
 * Hàm này KHÔNG BAO GIỜ bị block.
 */
void loop() {
  // 0. (ĐÃ SỬA) Kiểm tra hẹn giờ đóng servo (Non-Blocking)
  if (servoCloseTime > 0 && millis() >= servoCloseTime) {
    myServo.write(0);
    servoCloseTime = 0; // Đặt về 0 để báo là đã đóng
    Serial.println("Servo đã đóng (non-blocking).");
  }

  // 1. Luôn duy trì WiFi
  maintainWiFi();

  // 2. Chạy State Machine
  switch (currentState) {
    case STATE_IDLE:
      handleIdleState();
      break;
    case STATE_POLLING:
      handlePollingState();
      break;
  }
  
  // Cho 1 delay nhỏ để ESP32 "thở"
  delay(10); 
}


// ================= HÀM XỬ LÝ TRẠNG THÁI =================

/**
 * @brief Xử lý khi ở trạng thái IDLE (chờ quét).
 */
void handleIdleState() {
  // 1. Chờ thẻ mới
  if (!mfrc522.PICC_IsNewCardPresent()) {
    return;
  }

  // 2. Đọc UID thẻ (Chỉ đọc 1 lần)
  if (!mfrc522.PICC_ReadCardSerial()) {
    return;
  }
  
  // 3. Thẻ đã được đọc. Kiểm tra Cooldown (debounce)
  unsigned long now = millis();
  if (now - lastTriggerTime < COOL_DOWN_MS) {
    Serial.println("Cooldown... Bỏ qua.");
    mfrc522.PICC_HaltA(); 
    return;
  }
  // Không cập nhật lastTriggerTime ở đây, chỉ cập nhật khi server trả về OK

  // 4. Xử lý API
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Lỗi: Mất WiFi.");
    mfrc522.PICC_HaltA();
    return;
  }

  String cardUid = getCardUID(mfrc522.uid);
  Serial.printf("Thẻ quét: %s\n", cardUid.c_str());

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

  Serial.println("Gửi yêu cầu VÀO/RA...");
  int httpResponseCode = http.POST(jsonPayload);
  
  if (httpResponseCode > 0) {
    String responsePayload = http.getString();
    Serial.printf("Server: %s\n", responsePayload.c_str());

    StaticJsonDocument<256> responseDoc;
    deserializeJson(responseDoc, responsePayload);

    const char* action = responseDoc["action"];
    
    if (action && strcmp(action, "open") == 0) {
      Serial.println("✅ Mở cửa (Tự động)");
      triggerOpen(); // (ĐÃ SỬA) Hàm này giờ không block
      lastTriggerTime = millis(); // Cập nhật cooldown
    } 
    else if (action && strcmp(action, "poll") == 0) {
      int pollId = responseDoc["poll_id"];
      startPolling(pollId); // Chuyển sang trạng thái POLLING
    } 
    else {
      Serial.println("❌ Server từ chối. Không mở.");
      lastTriggerTime = millis(); // Cập nhật cooldown
    }
  } else {
    Serial.printf("Lỗi HTTP POST: %s\n", http.errorToString(httpResponseCode).c_str());
    lastTriggerTime = millis(); // Cập nhật cooldown
  }

  http.end();
  
  // 5. Dừng thẻ (luôn luôn)
  mfrc522.PICC_HaltA();
}

/**
 * @brief Xử lý khi ở trạng thái POLLING (chờ duyệt).
 * Hàm này không chặn (non-blocking).
 */
void handlePollingState() {
  unsigned long now = millis();

  // 1. Kiểm tra Timeout
  if (now - pollingStartTime > POLLING_TIMEOUT) {
    Serial.println("\n❌ Hết thời gian chờ duyệt.");
    stopPolling();
    return;
  }

  // 2. Kiểm tra Interval (chưa đến 1s)
  if (now - lastPollCheck < POLLING_INTERVAL) {
    return; // Chưa đến lúc, thoát ra (để loop() chạy)
  }

  // 3. Đã đến lúc hỏi server
  lastPollCheck = now;
  Serial.print("."); // In ra dấu chấm để báo là đang chờ

  if (WiFi.status() != WL_CONNECTED) {
     Serial.println("Mất WiFi khi đang chờ duyệt.");
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
      Serial.println("\n✅ Đã được duyệt! Mở cửa.");
      triggerOpen(); // (ĐÃ SỬA) Hàm này giờ không block
      stopPolling(); // Quay về IDLE
    }
    else if (status && strcmp(status, "denied") == 0) {
      Serial.println("\n❌ Bị bảo vệ từ chối.");
      stopPolling(); // Quay về IDLE
    }
    // Nếu là "pending", không làm gì, chờ lần poll sau
    
  } else {
    Serial.print("!"); // Lỗi poll
  }
  
  httpPoll.end();
}

/**
 * @brief Chuyển sang trạng thái chờ
 */
void startPolling(int pollId) {
  Serial.printf("Chờ bảo vệ duyệt (ID: %d)...\n", pollId);
  currentState = STATE_POLLING;
  currentPollId = pollId;
  pollingStartTime = millis();
  lastPollCheck = millis(); // Bắt đầu hỏi ngay
}

/**
 * @brief Thoát khỏi trạng thái chờ
 */
void stopPolling() {
  currentState = STATE_IDLE;
  currentPollId = 0;
  lastTriggerTime = millis(); // Bắt đầu cooldown sau khi kết thúc
  Serial.println("Chờ rút thẻ...");
  while(mfrc522.PICC_IsNewCardPresent()) {
    delay(50);
  }
  Serial.println("Sẵn sàng quét thẻ mới.");
}


// ================= HÀM TIỆN ÍCH =================

/**
 * @brief Chuyển đổi UID sang String
 */
String getCardUID(MFRC522::Uid uid) {
  String uidString = "";
  for (byte i = 0; i < uid.size; i++) {
    char hex[4];
    sprintf(hex, "%02X", uid.uidByte[i]);
    uidString += String(hex);
    if (i < uid.size - 1) {
      uidString += " ";
    }
  }
  return uidString;
}

/**
 * @brief Kích hoạt servo mở (NON-BLOCKING) (ĐÃ SỬA)
 */
void triggerOpen() {
  myServo.write(90); 
  // Chỉ hẹn giờ, không đợi
  servoCloseTime = millis() + OPEN_TIME_MS; 
  Serial.println("Servo đã mở, đang hẹn giờ đóng...");
}

// ================= HÀM WIFI =================

void connectWiFi(unsigned long timeout_ms) {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.printf("Đang kết nối WiFi tới \"%s\"...\n", WIFI_SSID);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - start) < timeout_ms) {
    delay(250);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("✅ Đã kết nối WiFi. IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("⚠️ Kết nối WiFi thất bại (timeout).");
  }
}

void maintainWiFi() {
  static unsigned long lastCheck = 0;
  const unsigned long CHECK_EVERY_MS = 10000UL; 
  if (millis() - lastCheck >= CHECK_EVERY_MS) {
    lastCheck = millis();
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("WiFi bị ngắt. Thử kết nối lại...");
      connectWiFi(7000UL);
    }
  }
}