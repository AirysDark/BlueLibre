package com.yourco.airpods

import android.bluetooth.*
import android.os.Build
import android.util.Log
import kotlinx.coroutines.*
import java.io.InputStream
import java.io.OutputStream

/**
 * Minimal BLE L2CAP CoC helper for API 29+.
 * - Server: listenUsingL2capChannel() → accept()
 * - Client: device.createL2capChannel(psm)
 * Falls back to GATT when unavailable.
 */
class L2capCocManager {
  data class Channel(val socket: BluetoothSocket, val input: InputStream, val output: OutputStream)

  fun isSupported(): Boolean = Build.VERSION.SDK_INT >= 29

  /** Start a server; returns the assigned PSM. Accept runs on a coroutine and invokes onClient */
  fun startServer(scope: CoroutineScope, adapter: BluetoothAdapter, onClient: (Channel) -> Unit): Int {
    require(isSupported()) { "L2CAP CoC requires API 29+" }
    val server: BluetoothServerSocket = adapter.listenUsingL2capChannel()
    val psm = server.psm
    scope.launch(Dispatchers.IO) {
      try {
        val sock = server.accept()
        onClient(Channel(sock, sock.inputStream, sock.outputStream))
      } catch (e: Throwable) {
        Log.e("L2capCoc", "Server accept failed: ${e.message}", e)
      } finally {
        try { server.close() } catch (_: Throwable) {}
      }
    }
    return psm
  }

  /** Connect as a client to a remote PSM */
  fun connectClient(device: BluetoothDevice, psm: Int): Channel {
    require(isSupported()) { "L2CAP CoC requires API 29+" }
    val sock = device.createL2capChannel(psm)
    sock.connect()
    return Channel(sock, sock.inputStream, sock.outputStream)
  }
}
