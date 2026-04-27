package qa.qu.trakn.aptool.ui.map

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.rememberTransformableState
import androidx.compose.foundation.gestures.transformable
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CenterFocusStrong
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import coil.request.ImageRequest
import qa.qu.trakn.aptool.data.models.ScannedAp
import qa.qu.trakn.aptool.ui.scan.ScanViewModel
import qa.qu.trakn.aptool.ui.scan.StatRow
import qa.qu.trakn.aptool.ui.scan.rssiColor
import qa.qu.trakn.aptool.ui.theme.Green
import qa.qu.trakn.aptool.ui.theme.Orange
import qa.qu.trakn.aptool.ui.theme.Yellow

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MapScreen(
    viewModel: MapViewModel,
    scanViewModel: ScanViewModel,
) {
    val state     by viewModel.state.collectAsState()
    val snackbarHostState = remember { SnackbarHostState() }
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    LaunchedEffect(state.snackbarMsg) {
        state.snackbarMsg?.let {
            snackbarHostState.showSnackbar(it)
            viewModel.clearSnackbar()
        }
    }

    var scale by remember { mutableFloatStateOf(1f) }
    var offset by remember { mutableStateOf(Offset.Zero) }
    val transformState = rememberTransformableState { zoomChange, panChange, _ ->
        scale = (scale * zoomChange).coerceIn(0.5f, 8f)
        offset += panChange
    }

    // Actual intrinsic size of the loaded floor plan image.
    // Updated via AsyncImage onSuccess so Canvas and tap math always use real dimensions.
    var imgNaturalW by remember { mutableFloatStateOf(FLOOR_PLAN_PX_W) }
    var imgNaturalH by remember { mutableFloatStateOf(FLOOR_PLAN_PX_H) }

    Box(modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {

        // Instruction banner
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(Orange.copy(alpha = 0.85f))
                .padding(vertical = 6.dp)
                .align(Alignment.TopCenter),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                "Stand 1 m from an AP → tap its position on the map → hold 5 s",
                color = Color.White, fontSize = 11.sp, fontFamily = FontFamily.Monospace,
            )
        }

        // Floor plan + markers
        Box(
            modifier = Modifier
                .fillMaxSize()
                .transformable(transformState)
                .pointerInput(imgNaturalW, imgNaturalH) {
                    detectTapGestures { tapOffset ->
                        val canvasW = size.width.toFloat()
                        val canvasH = size.height.toFloat()
                        // ContentScale.Fit scale factor for the real image dimensions
                        val fitScale = minOf(canvasW / imgNaturalW, canvasH / imgNaturalH)
                        val displayedW = imgNaturalW * fitScale
                        val displayedH = imgNaturalH * fitScale
                        val imgLeft = (canvasW - displayedW * scale) / 2 + offset.x
                        val imgTop  = (canvasH - displayedH * scale) / 2 + offset.y

                        // Convert tap → floor plan natural pixels
                        val xOnImg = (tapOffset.x - imgLeft) / (scale * fitScale)
                        val yOnImg = (tapOffset.y - imgTop)  / (scale * fitScale)

                        if (xOnImg in 0f..imgNaturalW && yOnImg in 0f..imgNaturalH) {
                            viewModel.onMapTap(xOnImg, yOnImg)
                        }
                    }
                }
        ) {
            val context = LocalContext.current

            if (state.floorPlanUrl != null) {
                AsyncImage(
                    model = ImageRequest.Builder(context)
                        .data(state.floorPlanUrl)
                        .crossfade(true)
                        .build(),
                    contentDescription = "Floor plan",
                    contentScale = ContentScale.Fit,
                    onSuccess = { result ->
                        imgNaturalW = result.painter.intrinsicSize.width.takeIf { it > 0 } ?: FLOOR_PLAN_PX_W
                        imgNaturalH = result.painter.intrinsicSize.height.takeIf { it > 0 } ?: FLOOR_PLAN_PX_H
                    },
                    modifier = Modifier
                        .fillMaxSize()
                        .graphicsLayer(
                            scaleX = scale, scaleY = scale,
                            translationX = offset.x, translationY = offset.y,
                        ),
                )
            } else {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(24.dp)) {
                        Text("No floor plan", color = Yellow, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
                        Text(
                            state.floorPlanError ?: "Upload one in the Web Mapping Tool first.",
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                            fontSize = 11.sp,
                            modifier = Modifier.padding(top = 4.dp),
                            textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                        )
                    }
                }
            }

            // Grid + AP markers — coordinate system matches ContentScale.Fit display
            Canvas(
                modifier = Modifier
                    .fillMaxSize()
                    .graphicsLayer(
                        scaleX = scale, scaleY = scale,
                        translationX = offset.x, translationY = offset.y,
                    )
            ) {
                val canvasW = size.width
                val canvasH = size.height
                val fitScale = minOf(canvasW / imgNaturalW, canvasH / imgNaturalH)
                val startX = (canvasW - imgNaturalW * fitScale) / 2
                val startY = (canvasH - imgNaturalH * fitScale) / 2

                // Grid dots (coords in metres → natural px → screen px)
                state.gridPoints.forEach { pt ->
                    val xPx = startX + pt.x.toFloat() * state.gridScale * fitScale
                    val yPx = startY + pt.y.toFloat() * state.gridScale * fitScale
                    drawCircle(
                        color = Color(0xFF3B82F6).copy(alpha = 0.55f),
                        radius = 4f,
                        center = Offset(xPx, yPx),
                    )
                }

                // AP markers (drawn on top of grid)
                state.placedAps.forEach { ap ->
                    val xPx = startX + ap.x.toFloat() * SCALE_PX_PER_M * fitScale
                    val yPx = startY + ap.y.toFloat() * SCALE_PX_PER_M * fitScale
                    drawApMarker(this, xPx, yPx, Orange)
                }
            }
        }

        // Floor plan error banner — visible on top of grid
        if (state.floorPlanUrl == null && state.floorPlanError != null) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .align(Alignment.BottomCenter)
                    .background(MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.92f))
                    .padding(10.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    state.floorPlanError!!,
                    color = MaterialTheme.colorScheme.onErrorContainer,
                    fontSize = 11.sp,
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                )
            }
        }

        // Reset view FAB
        FloatingActionButton(
            onClick = { scale = 1f; offset = Offset.Zero },
            containerColor = MaterialTheme.colorScheme.surface,
            modifier = Modifier
                .align(Alignment.CenterEnd)
                .padding(end = 12.dp)
                .size(44.dp),
        ) {
            Icon(Icons.Default.CenterFocusStrong, contentDescription = "Reset view", modifier = Modifier.size(20.dp))
        }

        // Capturing overlay — shown during 5s RSSI scan
        state.capturingProgress?.let { progress ->
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(Color.Black.copy(alpha = 0.55f)),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    CircularProgressIndicator(
                        progress = { progress },
                        color    = Orange,
                        modifier = Modifier.size(72.dp),
                        strokeWidth = 6.dp,
                    )
                    Spacer(Modifier.height(16.dp))
                    Text(
                        "Capturing RSSI… ${(progress * 5).toInt() + 1} / 5 s",
                        color = Color.White,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        "Stay still near the AP",
                        color = Color.White.copy(alpha = 0.7f),
                        fontSize = 12.sp,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                }
            }
        }

        SnackbarHost(snackbarHostState, modifier = Modifier.align(Alignment.BottomCenter))
    }

    // Confirm placement sheet
    val tapM = state.pendingTapM
    if (state.showConfirmSheet && state.pendingGroup.isNotEmpty() && tapM != null) {
        ModalBottomSheet(
            onDismissRequest = { viewModel.cancelPlacement() },
            sheetState = sheetState,
            containerColor = MaterialTheme.colorScheme.surfaceVariant,
        ) {
            ConfirmPlacementSheet(
                group  = state.pendingGroup,
                tapM   = tapM,
                onConfirm = { viewModel.confirmPlacement() },
                onCancel  = { viewModel.cancelPlacement() },
            )
        }
    }
}

fun drawApMarker(scope: DrawScope, xPx: Float, yPx: Float, color: Color) {
    val center = Offset(xPx, yPx)
    listOf(30f, 22f, 14f).forEachIndexed { i, r ->
        scope.drawCircle(color.copy(alpha = 0.06f + i * 0.02f), radius = r, center = center)
    }
    scope.drawCircle(color.copy(alpha = 0.4f), radius = 14f, center = center, style = Stroke(1.5f))
    scope.drawCircle(color, radius = 8f, center = center)
    scope.drawCircle(Color.White.copy(alpha = 0.4f), radius = 3f, center = center)
}

@Composable
fun ConfirmPlacementSheet(
    group: List<ScannedAp>,
    tapM: Pair<Double, Double>,
    onConfirm: () -> Unit,
    onCancel: () -> Unit,
) {
    val primary = group.first()
    val posStr  = "(${String.format("%.1f", tapM.first)} m, ${String.format("%.1f", tapM.second)} m)"

    Column(modifier = Modifier.padding(16.dp).fillMaxWidth()) {
        Text("Confirm AP Location", fontWeight = FontWeight.Bold, fontSize = 16.sp)
        Text(
            if (group.size == 1)
                "The strongest visible AP will be recorded at this position."
            else
                "${group.size} BSSIDs from the same physical AP will be recorded at this position.",
            fontSize = 12.sp,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
            modifier = Modifier.padding(top = 2.dp, bottom = 12.dp),
        )

        Card(
            colors = CardDefaults.cardColors(containerColor = Green.copy(alpha = 0.08f)),
            modifier = Modifier.fillMaxWidth(),
            border = androidx.compose.foundation.BorderStroke(1.dp, Green.copy(alpha = 0.4f)),
            shape = RoundedCornerShape(8.dp),
        ) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                Text(
                    if (group.size == 1) "STRONGEST AP" else "AP GROUP  (${group.size} BSSIDs)",
                    fontSize = 10.sp, color = Green, fontWeight = FontWeight.Bold,
                )
                StatRow("SSID",     primary.ssid)
                StatRow("Position", posStr)
                Spacer(Modifier.height(4.dp))
                // List every BSSID in the group
                LazyColumn(
                    verticalArrangement = Arrangement.spacedBy(3.dp),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    items(group) { ap ->
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                ap.bssid,
                                fontSize = 11.sp,
                                fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace,
                                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.85f),
                            )
                            Text(
                                "${ap.rssi} dBm",
                                fontSize = 11.sp,
                                color = rssiColor(ap.rssi),
                                fontWeight = FontWeight.SemiBold,
                            )
                        }
                    }
                }
            }
        }

        Spacer(Modifier.height(14.dp))
        Button(
            onClick = onConfirm,
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(containerColor = Green),
        ) {
            Text(if (group.size == 1) "Save AP at this location" else "Save ${group.size} BSSIDs at this location")
        }
        OutlinedButton(onClick = onCancel, modifier = Modifier.fillMaxWidth().padding(top = 6.dp)) {
            Text("Cancel")
        }
        Spacer(Modifier.height(16.dp))
    }
}
