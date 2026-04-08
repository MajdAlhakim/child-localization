package qa.qu.trakn.aptool.ui.status

import androidx.compose.foundation.background
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
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Divider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import qa.qu.trakn.aptool.data.models.AccessPoint
import qa.qu.trakn.aptool.ui.scan.StatRow
import qa.qu.trakn.aptool.ui.theme.Green
import qa.qu.trakn.aptool.ui.theme.Orange
import qa.qu.trakn.aptool.ui.theme.Red
import qa.qu.trakn.aptool.ui.theme.Yellow

@Composable
fun StatusScreen(viewModel: StatusViewModel) {
    val state by viewModel.state.collectAsState()
    val snackbarState = remember { SnackbarHostState() }

    LaunchedEffect(state.snackbarMsg) {
        state.snackbarMsg?.let { snackbarState.showSnackbar(it); viewModel.clearSnackbar() }
    }

    Box(modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        Column(modifier = Modifier.fillMaxSize()) {
            // Header row
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(MaterialTheme.colorScheme.surface)
                    .padding(12.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    // Connection dot
                    Box(
                        modifier = Modifier
                            .size(10.dp)
                            .clip(CircleShape)
                            .background(if (state.backendConnected) Green else Red)
                    )
                    Spacer(Modifier.width(6.dp))
                    Text(
                        if (state.backendConnected) "Backend connected" else "Backend offline",
                        fontSize = 12.sp,
                        color = if (state.backendConnected) Green else Red,
                        fontFamily = FontFamily.Monospace,
                    )
                }
                // AP count badge
                val countColor = when {
                    state.aps.size >= 3 -> Green
                    state.aps.isEmpty() -> Red
                    else -> Yellow
                }
                Text(
                    "${state.aps.size} APs placed",
                    color = countColor, fontWeight = FontWeight.SemiBold, fontSize = 13.sp,
                )
            }

            if (state.aps.isEmpty()) {
                Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("No APs placed yet", color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f))
                        Text("Use the Scan tab to measure and place APs.", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.3f), modifier = Modifier.padding(top = 4.dp))
                    }
                }
            } else {
                LazyColumn(modifier = Modifier.weight(1f).padding(8.dp)) {
                    items(state.aps, key = { it.bssid }) { ap ->
                        ApStatusCard(ap)
                    }
                }
            }

            // Delete all
            OutlinedButton(
                onClick = { viewModel.requestDeleteAll() },
                modifier = Modifier.fillMaxWidth().padding(12.dp),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = Red),
                border = androidx.compose.foundation.BorderStroke(1.dp, Red.copy(alpha = 0.5f)),
                enabled = !state.isDeleting && state.aps.isNotEmpty(),
            ) {
                if (state.isDeleting) {
                    CircularProgressIndicator(modifier = Modifier.size(16.dp), strokeWidth = 2.dp, color = Red)
                    Spacer(Modifier.width(6.dp))
                }
                Text("Clear All APs")
            }
        }

        SnackbarHost(snackbarState, modifier = Modifier.align(Alignment.BottomCenter))
    }

    // Delete confirmation dialog
    if (state.showDeleteConfirm) {
        AlertDialog(
            onDismissRequest = { viewModel.dismissDeleteConfirm() },
            containerColor = MaterialTheme.colorScheme.surface,
            title = { Text("Clear all APs?") },
            text = { Text("This will permanently delete all ${state.aps.size} placed APs from the backend. This cannot be undone.") },
            confirmButton = {
                Button(
                    onClick = { viewModel.confirmDeleteAll() },
                    colors = ButtonDefaults.buttonColors(containerColor = Red),
                ) { Text("Delete all") }
            },
            dismissButton = {
                TextButton(onClick = { viewModel.dismissDeleteConfirm() }) { Text("Cancel") }
            }
        )
    }
}

@Composable
fun ApStatusCard(ap: AccessPoint) {
    Card(
        modifier = Modifier.fillMaxWidth().padding(vertical = 3.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        shape = RoundedCornerShape(8.dp),
    ) {
        Column(Modifier.padding(10.dp)) {
            Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                Text(ap.ssid.ifBlank { "<no ssid>" }, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                Box(
                    modifier = Modifier.size(8.dp).clip(CircleShape).background(Orange).align(Alignment.CenterVertically)
                )
            }
            Text(ap.bssid, fontFamily = FontFamily.Monospace, fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
            Divider(modifier = Modifier.padding(vertical = 6.dp), color = MaterialTheme.colorScheme.outline.copy(alpha = 0.3f))
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("(${"%.1f".format(ap.x)} m, ${"%.1f".format(ap.y)} m)", fontFamily = FontFamily.Monospace, fontSize = 11.sp)
                Text("${ap.rssiRef.toInt()} dBm / n=${ap.pathLossN}", fontFamily = FontFamily.Monospace, fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
            }
        }
    }
}
