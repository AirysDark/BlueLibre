package com.yourco.airpods

object NativeBridge {
  init { System.loadLibrary("airpods_core") }
  external fun parseAirPodsPayload(payload: ByteArray): String
}
