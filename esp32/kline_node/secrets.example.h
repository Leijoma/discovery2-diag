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

// WireGuard client (optional) — gives the node a FIXED tunnel IP reachable from the
// phone via WG, so you never chase its hotspot DHCP address. Leave WG_PRIVATE_KEY as
// the placeholder to disable WG. Generate a keypair with: wg genkey | wg pubkey
#define WG_LOCAL_IP    "10.9.0.9"                 // this node's WG address
#define WG_PRIVATE_KEY "esp-private-key-here"     // from wg genkey (keep secret)
#define WG_PEER_PUBKEY "wg-server-public-key"     // your WG server's public key
#define WG_ENDPOINT    "your.wg.server"           // WG server host/IP
#define WG_PORT        51820
