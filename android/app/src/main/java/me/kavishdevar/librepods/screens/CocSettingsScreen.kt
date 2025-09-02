package me.kavishdevar.librepods.screens

import android.content.Context
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import me.kavishdevar.librepods.utils.SettingsManager

@Composable
fun CocSettingsScreen(context: Context) {
    var checked by remember { mutableStateOf(SettingsManager.isUseCoc(context)) }

    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text("Connection Settings", style = MaterialTheme.typography.headlineSmall)
        Spacer(Modifier.height(12.dp))
        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            Checkbox(checked = checked, onCheckedChange = {
                checked = it
                SettingsManager.setUseCoc(context, it)
            })
            Spacer(Modifier.width(8.dp))
            Text("Prefer high-throughput L2CAP (CoC) when available")
        }
    }
}
