package qa.qu.trakn.aptool.ui.scan

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.NetworkWifi
import androidx.compose.material.icons.filled.NetworkWifi1Bar
import androidx.compose.material.icons.filled.NetworkWifi2Bar
import androidx.compose.material.icons.filled.NetworkWifi3Bar
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SuggestionChip
import androidx.compose.material3.SuggestionChipDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import qa.qu.trakn.aptool.data.models.ScannedAp
import qa.qu.trakn.aptool.ui.theme.Blue
import qa.qu.trakn.aptool.ui.theme.Green
import qa.qu.trakn.aptool.ui.theme.Orange
import qa.qu.trakn.aptool.ui.theme.Red
import qa.qu.trakn.aptool.ui.theme.Yellow

@Composable
fun ScanScreen(viewModel: ScanViewModel) {
    val state by viewModel.state.collectAsState()
    val bestBssid = viewModel.bestAp?.bssid

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
    ) {
        // Header
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(MaterialTheme.colorScheme.surface)
                .padding(horizontal = 16.dp, vertical = 10.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("AP Scanner", fontWeight = FontWeight.Bold, fontSize = 16.sp)
            Row(verticalAlignment = Alignment.CenterVertically) {
                ScanningDot(scanning = state.isScanning)
                Spacer(Modifier.width(6.dp))
                Text(
                    "${state.aps.size} APs visible",
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                    fontFamily = FontFamily.Monospace,
                )
            }
        }

        // Best AP banner
        if (bestBssid != null) {
            val best = state.aps.first { it.bssid == bestBssid }
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(Green.copy(alpha = 0.1f))
                    .padding(horizontal = 16.dp, vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text("STRONGEST:", fontSize = 10.sp, color = Green, fontWeight = FontWeight.Bold, fontFamily = FontFamily.Monospace)
                Text(best.ssid, fontSize = 11.sp, color = Green, fontWeight = FontWeight.SemiBold)
                Text(best.bssid, fontSize = 10.sp, color = Green.copy(alpha = 0.7f), fontFamily = FontFamily.Monospace)
                Spacer(Modifier.weight(1f))
                Text("${best.rssi} dBm", fontSize = 11.sp, color = Green, fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold)
            }
        }

        Text(
            "Go to Map tab, tap your location — the strongest AP will be recorded automatically.",
            fontSize = 11.sp,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.45f),
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp),
        )

        LazyColumn(modifier = Modifier.fillMaxSize().padding(8.dp)) {
            items(state.aps, key = { it.bssid }) { ap ->
                ApCard(ap = ap, isBest = ap.bssid == bestBssid)
            }
        }
    }
}

@Composable
fun ScanningDot(scanning: Boolean) {
    val transition = rememberInfiniteTransition(label = "scan")
    val alpha by transition.animateFloat(
        initialValue = 0.3f, targetValue = 1f, label = "alpha",
        animationSpec = infiniteRepeatable(tween(800, easing = LinearEasing), RepeatMode.Reverse),
    )
    Box(
        modifier = Modifier
            .size(8.dp)
            .clip(CircleShape)
            .background(if (scanning) Green.copy(alpha = alpha) else Color.Gray)
    )
}

@Composable
fun ApCard(ap: ScannedAp, isBest: Boolean) {
    val borderColor = when {
        isBest -> Green
        else -> MaterialTheme.colorScheme.outline.copy(alpha = 0.3f)
    }
    val bgColor = when {
        isBest -> Green.copy(alpha = 0.07f)
        else -> MaterialTheme.colorScheme.surface
    }
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 3.dp)
            .border(1.dp, borderColor, RoundedCornerShape(8.dp)),
        colors = CardDefaults.cardColors(containerColor = bgColor),
        shape = RoundedCornerShape(8.dp),
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            SignalIcon(rssi = ap.rssi)
            Spacer(Modifier.width(10.dp))
            Column(modifier = Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(ap.ssid, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                    if (isBest) {
                        Text("BEST", fontSize = 9.sp, color = Green, fontWeight = FontWeight.Bold,
                            modifier = Modifier.background(Green.copy(alpha = 0.15f), RoundedCornerShape(4.dp)).padding(horizontal = 4.dp, vertical = 1.dp))
                    }
                }
                Text(ap.bssid, fontFamily = FontFamily.Monospace, fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(top = 4.dp)) {
                    Text("${ap.rssi} dBm", fontSize = 11.sp, fontFamily = FontFamily.Monospace, color = rssiColor(ap.rssi))
                    Text("${ap.frequencyMhz} MHz", fontSize = 10.sp, fontFamily = FontFamily.Monospace, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f))
                    if (ap.rttSupported) {
                        Text("802.11mc", fontSize = 10.sp, color = Blue)
                    }
                }
            }
            if (ap.alreadyPlaced) {
                SuggestionChip(
                    onClick = {},
                    label = { Text("✓ Placed", fontSize = 10.sp) },
                    colors = SuggestionChipDefaults.suggestionChipColors(
                        containerColor = Green.copy(alpha = 0.15f),
                        labelColor = Green,
                    ),
                    border = SuggestionChipDefaults.suggestionChipBorder(enabled = true, borderColor = Green.copy(alpha = 0.4f)),
                    modifier = Modifier.height(24.dp),
                )
            }
        }
    }
}

@Composable
fun SignalIcon(rssi: Int) {
    val icon = when {
        rssi >= -50 -> Icons.Default.NetworkWifi
        rssi >= -65 -> Icons.Default.NetworkWifi3Bar
        rssi >= -75 -> Icons.Default.NetworkWifi2Bar
        else -> Icons.Default.NetworkWifi1Bar
    }
    androidx.compose.material3.Icon(icon, contentDescription = null, tint = rssiColor(rssi), modifier = Modifier.size(20.dp))
}

fun rssiColor(rssi: Int): Color = when {
    rssi >= -60 -> Green
    rssi >= -75 -> Yellow
    else -> Red
}

@Composable
fun StatRow(label: String, value: String, color: Color = MaterialTheme.colorScheme.onSurface) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
        Text(value, fontSize = 12.sp, fontFamily = FontFamily.Monospace, color = color)
    }
}
