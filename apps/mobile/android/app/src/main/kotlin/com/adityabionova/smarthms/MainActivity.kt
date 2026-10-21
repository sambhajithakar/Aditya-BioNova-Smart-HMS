package com.adityabionova.smarthms

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/**
 * Hosts a small channel that asks for the Bluetooth runtime permissions used
 * by M8.2 device capture (lib/devices/ble_transport.dart). Nothing else.
 * Android 12+: BLUETOOTH_SCAN + BLUETOOTH_CONNECT; older: ACCESS_FINE_LOCATION
 * (required by the platform for BLE scans).
 */
class MainActivity : FlutterActivity() {
    private var pending: MethodChannel.Result? = null

    private fun needed(): Array<String> =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
        } else {
            arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
        }

    private fun granted(): Boolean = needed().all {
        ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "status" -> result.success(if (granted()) "granted" else "denied")
                    "request" -> {
                        if (granted()) {
                            result.success("granted")
                        } else if (pending != null) {
                            result.error("busy", "A permission request is already open", null)
                        } else {
                            pending = result
                            ActivityCompat.requestPermissions(this, needed(), REQUEST)
                        }
                    }
                    else -> result.notImplemented()
                }
            }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<out String>, grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != REQUEST) return
        val result = pending ?: return
        pending = null
        val ok = grantResults.isNotEmpty() &&
            grantResults.all { it == PackageManager.PERMISSION_GRANTED }
        result.success(
            when {
                ok -> "granted"
                // "don't ask again": only the system settings can grant it now
                permissions.any { !ActivityCompat.shouldShowRequestPermissionRationale(this, it) } ->
                    "permanently_denied"
                else -> "denied"
            },
        )
    }

    companion object {
        private const val CHANNEL = "com.adityabionova.smarthms/ble_permissions"
        private const val REQUEST = 4182
    }
}
