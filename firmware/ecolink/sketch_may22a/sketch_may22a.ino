#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_NeoPixel.h>

#define POT_B_PIN   32   
#define LDR_PIN     35   
#define LED_PIN     25   
#define BUZZER_PIN  18   
#define STRIP_PIN   19    

#define NUM_LEDS    30   
#define SCREEN_WIDTH 128 
#define SCREEN_HEIGHT 64

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);
Adafruit_NeoPixel strip(NUM_LEDS, STRIP_PIN, NEO_GRB + NEO_KHZ800);

// ===== WiFi =====
const char* WIFI_SSID     = "Lishan"; 
const char* WIFI_PASSWORD = "12345678";
const char* SERVER_URL    = "http://172.20.10.3:5000/api/data"; 

float kwhB = 275.0; 
float kwhA = 150.0;
float kwhC = 500.0;

// ==========================================

void drawPage_SolarDropping() {
    display.clearDisplay(); display.setTextColor(WHITE);
    display.setTextSize(1); display.setCursor(15, 0);
    display.println("ECOLINK SCHEDULER"); display.drawLine(0, 10, 128, 10, WHITE); 
    
    display.setCursor(0, 20); display.println("Status: Cloudy");
    display.setCursor(0, 32); display.println(">>> SOLAR DROPPING");
    
    display.setCursor(0, 46); display.println("Action: Shift Loads");
    display.setCursor(0, 56); display.println("Grid Active (Blue)");
    display.display();
}

void drawPage_TierWarning(float kwh) {
    display.clearDisplay(); display.setTextColor(WHITE);
    display.setTextSize(1); display.setCursor(15, 0);
    display.println("! TIER WARNING !"); display.drawLine(0, 10, 128, 10, WHITE); 
    
    display.setCursor(0, 18); display.print("House B: "); display.print(kwh, 1); display.println(" kWh");
    display.setCursor(0, 30); display.print("Tier Jump: "); display.print(300.0 - kwh, 1); display.println("kWh");
    display.setCursor(0, 42); display.println("Rate: +53% !!");
    display.setCursor(0, 54); display.println("> Reduce AC 2h/day");
    display.display();
}

void drawPage_SolarSurplus() {
    display.clearDisplay(); display.setTextColor(WHITE);
    display.setTextSize(1); display.setCursor(15, 0);
    display.println("* SOLAR SURPLUS *"); display.drawLine(0, 10, 128, 10, WHITE); 
    
    display.setCursor(0, 18); display.println("A Output: 2.1 kW");
    display.setCursor(0, 30); display.println("C EV Charge: NOW");
    display.setCursor(0, 42); display.println("Save: RM 2.30");
    display.setCursor(0, 54); display.println("Best until 16:00");
    display.display();
}

void drawPage_Anomaly(int power) {
    display.clearDisplay(); display.setTextColor(WHITE);
    display.setTextSize(1); display.setCursor(15, 0);
    display.println("~ ANOMALY ALERT ~"); display.drawLine(0, 10, 128, 10, WHITE); 
    
    display.setCursor(0, 18); display.print("House B: "); display.print(power); display.println(" W");
    display.setCursor(0, 30); display.println("Normal:  320 W");
    
    display.setCursor(0, 42); display.print("Spike: +");
    int pct = (power / 320) * 100; display.print(pct); display.println("%");
    
    display.setCursor(0, 54); display.println("> Check appliances");
    display.display();
}


void setup() {
    Serial.begin(115200);
    delay(500);
    
    if(!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) Serial.println(F("OLED failed"));
    display.clearDisplay(); display.setTextColor(WHITE); display.setTextSize(1);
    display.setCursor(0, 20); display.println("Connecting WiFi..."); display.display();

    pinMode(LED_PIN, OUTPUT);
    pinMode(BUZZER_PIN, OUTPUT); 
    
    strip.begin();
    strip.setBrightness(40); 
    strip.show();

    analogSetPinAttenuation(POT_B_PIN, ADC_11db);
    analogSetPinAttenuation(LDR_PIN,   ADC_11db);
    
    connectWiFi();
}

void connectWiFi() {
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
}

void loop() {
    if (WiFi.status() == WL_CONNECTED) {
        
        int rawLDR = analogRead(LDR_PIN); 
        int solarPercent = map(rawLDR, 0, 4000, 0, 100);
        solarPercent = constrain(solarPercent, 0, 100);

        if (solarPercent >= 60) { 
            digitalWrite(LED_PIN, HIGH); 
        } else { 
            digitalWrite(LED_PIN, LOW); 
        }

        int rawPotB = analogRead(POT_B_PIN); 
        int powerB = map(rawPotB, 0, 4095, 0, 5000); 
        
        int powerA = 450; int powerC = 6500; 
        
        kwhA += (powerA / 3600000.0) * 1000; 
        kwhB += (powerB / 3600000.0) * 1000; 
        kwhC += (powerC / 3600000.0) * 1000;

        StaticJsonDocument<512> doc;
        doc["house_a"]["current_power"] = powerA; doc["house_a"]["kwh"] = round(kwhA * 10) / 10.0; doc["house_a"]["solar_percent"] = solarPercent; 
        doc["house_b"]["current_power"] = powerB; doc["house_b"]["kwh"] = round(kwhB * 10) / 10.0;
        doc["house_c"]["current_power"] = powerC; doc["house_c"]["kwh"] = round(kwhC * 10) / 10.0; doc["house_c"]["ev_charging"] = (powerC > 4000); 

        String jsonStr; serializeJson(doc, jsonStr);
        HTTPClient http; http.begin(SERVER_URL); http.addHeader("Content-Type", "application/json"); http.setTimeout(3000);
        int code = http.POST(jsonStr); http.end();
        Serial.printf("LDR: %d%% | B(Real): %dW | kWh: %.1f | Code: %d\n", solarPercent, powerB, kwhB, code);

        // =========================================================

        if (powerB > 3500) {
            drawPage_Anomaly(powerB);
            for(int i=0; i<10; i++) {
                strip.fill(strip.Color(255, 0, 0)); strip.show();
                digitalWrite(BUZZER_PIN, HIGH); delay(50);
                
                strip.clear(); strip.show();
                digitalWrite(BUZZER_PIN, LOW); delay(50);
            }
        }
        else if (kwhB >= 280.0 && kwhB < 290.0) {
            drawPage_TierWarning(kwhB);
            
            strip.clear();
            for(int j=10; j<=19; j++) strip.setPixelColor(j, strip.Color(200, 50, 0)); // 橘红色
            strip.show();
            delay(500); 
            
            strip.clear(); strip.show();
            delay(500); 
        }
        
        else if (kwhB >= 290.0 && kwhB < 300.0) {
            drawPage_TierWarning(kwhB);
            
            for(int i=0; i<2; i++) {
                strip.clear();
                for(int j=10; j<=19; j++) strip.setPixelColor(j, strip.Color(255, 0, 0)); // 变成纯正的红色
                strip.show();
                digitalWrite(BUZZER_PIN, HIGH); 
                delay(80);  
                
                strip.clear(); strip.show();
                digitalWrite(BUZZER_PIN, LOW); 
                delay(150); 
            }
            delay(500); 
        }
        else if (digitalRead(LED_PIN) == HIGH) {
            drawPage_SolarSurplus();
            int delayTime = 1000 / NUM_LEDS; 
            for(int i=0; i<NUM_LEDS; i++) {
                strip.clear();
                strip.setPixelColor(i, strip.Color(0, 255, 0)); 
                if(i > 0) strip.setPixelColor(i-1, strip.Color(0, 50, 0)); 
                strip.show();
                delay(delayTime);
            }
        }
        else {
            drawPage_SolarDropping();
            strip.fill(strip.Color(0, 0, 150)); 
            strip.show();
            delay(1000); 
        }

    } else {
        Serial.println("WiFi disconnected...");
        connectWiFi();
    }
}