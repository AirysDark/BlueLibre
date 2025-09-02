import me.kavishdevar.librepods.utils.SettingsManager
package com.yourco.airpods

import android.bluetooth.*
import android.bluetooth.le.*
import android.content.Context
import android.os.ParcelUuid
import java.util.*

private val SERVICE_UUID = UUID.fromString("D0611E78-BBB4-4591-A5F8-487910AE4366")
private val CHAR_UUID    = UUID.fromString("8667556C-9A37-4C91-84ED-54EE27D90049")

class BleClient(private val ctx: Context): BluetoothGattCallback() {
  private val coc = L2capCocManager()
  @Volatile private var useCocPreferred = SettingsManager.isUseCoc(ctx) // user setting, defaults true
  private val adapter = BluetoothAdapter.getDefaultAdapter()
  private val scanner get() = adapter?.bluetoothLeScanner

  fun startScan() {
    val filter = ScanFilter.Builder().setServiceUuid(ParcelUuid(SERVICE_UUID)).build()
    val settings = ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build()
    scanner?.startScan(listOf(filter), settings, scanCb)
  }

  private val scanCb = object: ScanCallback() {
    override fun onScanResult(type:Int, result:ScanResult) {
      scanner?.stopScan(this)
      result.device.connectGatt(ctx, false, this@BleClient, BluetoothDevice.TRANSPORT_LE)
    }
  }

  override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
    if (newState == BluetoothProfile.STATE_CONNECTED) gatt.discoverServices()
    if (newState == BluetoothProfile.STATE_DISCONNECTED) gatt.close()
  }

  override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
    val svc = gatt.getService(SERVICE_UUID) ?: return gatt.disconnect()
    val chr = svc.getCharacteristic(CHAR_UUID) ?: return gatt.disconnect()

    // Try L2CAP CoC if supported and PSM characteristic present; otherwise read data over GATT
    val psmChar = try { svc.getCharacteristic(UUID.fromString("0000FF01-0000-1000-8000-00805F9B34FB")) } catch (_: Throwable) { null }
    if (psmChar != null && coc.isSupported() && useCocPreferred) {
      // Read PSM
      gatt.readCharacteristic(psmChar)
      return
    }
    gatt.readCharacteristic(chr)
  }

  override fun onCharacteristicRead(gatt: BluetoothGatt, chr: BluetoothGattCharacteristic, status: Int) {
    if (status == BluetoothGatt.GATT_SUCCESS) {
      val bytes = chr.value

    // If we just read the PSM characteristic, try L2CAP CoC
    if (chr.uuid == UUID.fromString("0000FF01-0000-1000-8000-00805F9B34FB") && coc.isSupported() && useCocPreferred) {
      val psm = java.nio.ByteBuffer.wrap(bytes).order(java.nio.ByteOrder.LITTLE_ENDIAN).short.toInt() and 0xFFFF
      try {
        val ch = coc.connectClient(gatt.device, psm)
        // Example: request a simple info packet over CoC then close
        ch.output.write(byteArrayOf(0x01, 0x00)) // app-specific
        val tmp = ByteArray(128)
        val n = ch.input.read(tmp)
        // parse via JNI if it matches expected payload, else ignore
        gatt.disconnect()
        return
      } catch (e: Throwable) {
        // Fall back to GATT if CoC connect fails
        useCocPreferred = false
      }
    }
      val model = NativeBridge.parseAirPodsPayload(bytes)
    }
    gatt.disconnect()
  }
}
