# 🌿 EcoLink - Smart Energy Management

<div align="center">
  <img src="https://img.shields.io/badge/Hardware-ESP32-green?style=for-the-badge&logo=espressif" alt="ESP32">
  <img src="https://img.shields.io/badge/Backend-Python_Flask-blue?style=for-the-badge&logo=python" alt="Flask">
  <img src="https://img.shields.io/badge/Protocol-MQTT-purple?style=for-the-badge" alt="MQTT">
  <img src="https://img.shields.io/badge/Frontend-HTML%2FCSS%2FJS-orange?style=for-the-badge&logo=html5" alt="Frontend">
</div>

<br>

Developed by **Team EyeScream** (Yap Li Shan & Chan Min Huey).

EcoLink is an ultra-affordable (RM 41) IoT smart energy management system designed for Malaysian households. It helps families prevent expensive TNB tariff tier-jumps and enables neighborhood-level energy sharing by coordinating solar surplus with heavy loads like EVs.

## ✨ Key Features

* 📊 **TNB Tier-Jump Warning**: Predicts and alerts users 3-5 days before hitting the 53% tariff price surge.
* ⚡ **Anomaly Detection**: Identifies unusual power spikes in real-time to prevent energy waste and hazards.
* 👻 **Standby Power Estimation**: Translates idle "ghost loads" into wasted Ringgit (RM).
* 🤝 **Virtual Net Scheduling (VNS)**: Orchestrates community energy by notifying EV owners to charge when a neighbor's solar produces excess power.
* ⛅ **Weather-Driven Planning**: Uses MET Malaysia API to suggest optimal usage times based on solar forecasts.

## 🏗️ Tech Stack

* **Hardware**: ESP32-WROOM-32, SCT-013-030 (Non-invasive Current Sensor)
* **Backend**: Python Flask, SQLite
* **Communication**: MQTT (Mosquitto)
* **Frontend**: HTML5, CSS3, Vanilla JS, Chart.js

## 📂 Project Structure

```text
Ecolink/
├── backend/            # Python Flask server, MQTT subscriber, and analytics
├── firmware/           # C++ code for ESP32 (Sensor data & MQTT publish)
├── frontend/           # Web App UI (Dashboard, Alerts, Community Pages)
└── README.md           # Project documentation
