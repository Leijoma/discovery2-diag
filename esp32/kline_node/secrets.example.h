#pragma once
// Copy this file to `secrets.h` (gitignored) and fill in your values.
// The repo is public — real credentials must NEVER be committed.
//
// WiFi is tried in priority order: SSID_1 first, then SSID_2 (fallback).

#define WIFI_SSID_1 "SurfsUp"        // prio 1 — home network
#define WIFI_PW_1   "your-home-wifi-password"

#define WIFI_SSID_2 "Surfs"          // prio 2 — phone hotspot fallback
#define WIFI_PW_2   "your-hotspot-password"

#define OTA_HOSTNAME "kline-node"    // shows up as a network port for OTA flashing
#define OTA_PASSWORD "set-an-ota-password"
