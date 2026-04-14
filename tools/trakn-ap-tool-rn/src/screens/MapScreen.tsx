import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet,
  Modal, TextInput, ActivityIndicator, ScrollView, Alert,
} from 'react-native';
import { useStore } from '../store';
import { apApi, gridApi, getFloorPlanUrl } from '../api/client';
import FloorPlanMap from '../components/map/FloorPlanMap';
import { C, S, F } from '../theme';
import { useToastState } from '../hooks/useToast';

interface PlaceSheet {
  xM: number;
  yM: number;
  bssid: string;
  ssid: string;
  rssiRef: string;
  pathLossN: string;
  ceilingH: string;
}

const DEFAULT_SHEET: Omit<PlaceSheet, 'xM' | 'yM'> = {
  bssid: '',
  ssid: '',
  rssiRef: '-40',
  pathLossN: '2.5',
  ceilingH: '3.0',
};

function Field({
  label, value, onChange, keyboardType = 'default',
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  keyboardType?: 'default' | 'numeric' | 'decimal-pad';
}) {
  return (
    <View style={fStyles.wrap}>
      <Text style={fStyles.label}>{label}</Text>
      <TextInput
        style={fStyles.input}
        value={value}
        onChangeText={onChange}
        keyboardType={keyboardType}
        placeholderTextColor={C.textDim}
        autoCorrect={false}
        autoCapitalize="none"
      />
    </View>
  );
}

const fStyles = StyleSheet.create({
  wrap: { marginBottom: 10 },
  label: { fontSize: 10, color: C.textDim, fontFamily: F.mono, letterSpacing: 0.8, marginBottom: 4 },
  input: {
    backgroundColor: '#060a10', borderWidth: 1, borderColor: C.border,
    borderRadius: S.md, paddingHorizontal: 10, paddingVertical: 8,
    color: C.text, fontSize: 13, fontFamily: F.mono,
  },
});

export default function MapScreen() {
  const serverAps  = useStore(s => s.serverAps);
  const setServerAps = useStore(s => s.setServerAps);
  const grid       = useStore(s => s.grid);
  const setGrid    = useStore(s => s.setGrid);
  const scalePxPerM = useStore(s => s.scalePxPerM);
  const networks   = useStore(s => s.networks);
  const pending    = useStore(s => s.pendingPlacement);
  const setPending = useStore(s => s.setPendingPlacement);

  const [floorPlanUrl, setFloorPlanUrl] = useState<string | null>(null);
  const [sheet, setSheet] = useState<PlaceSheet | null>(null);
  const [saving, setSaving] = useState(false);
  const { toasts, toast } = useToastState();

  // Load floor plan URL + server data on mount
  useEffect(() => {
    getFloorPlanUrl().then(setFloorPlanUrl).catch(() => {});
    loadServerData();
  }, []);

  const loadServerData = async () => {
    try {
      const [apsRes, gridRes] = await Promise.all([
        apApi.list().catch(() => null),
        gridApi.get().catch(() => null),
      ]);
      if (apsRes) setServerAps(apsRes.access_points);
      if (gridRes) setGrid(gridRes);
    } catch {}
  };

  // Auto-fill BSSID from best scanned AP when sheet opens
  const openSheet = useCallback((xM: number, yM: number) => {
    const best = networks.length > 0
      ? [...networks].sort((a, b) => b.level - a.level)[0]
      : null;
    setSheet({
      xM, yM,
      bssid: best?.BSSID ?? '',
      ssid: best?.SSID ?? '',
      ...DEFAULT_SHEET,
    });
    setPending({ xMeters: xM, yMeters: yM });
  }, [networks, setPending]);

  const closeSheet = () => {
    setSheet(null);
    setPending(null);
  };

  const handlePlace = async () => {
    if (!sheet) return;
    if (!sheet.bssid.trim()) { toast('BSSID is required', 'error'); return; }
    setSaving(true);
    try {
      await apApi.place({
        bssid: sheet.bssid.trim(),
        ssid: sheet.ssid.trim(),
        rssi_ref: parseFloat(sheet.rssiRef) || -40,
        path_loss_n: parseFloat(sheet.pathLossN) || 2.5,
        x: sheet.xM,
        y: sheet.yM,
        ceiling_height: parseFloat(sheet.ceilingH) || 3.0,
      });
      toast(`AP placed: ${sheet.bssid.slice(-8)}`, 'success');
      closeSheet();
      await loadServerData();
    } catch (e: any) {
      toast(e?.response?.data?.detail ?? 'Failed to place AP', 'error');
    } finally {
      setSaving(false);
    }
  };

  const bestNetwork = networks.length > 0
    ? [...networks].sort((a, b) => b.level - a.level)[0]
    : null;

  const fillBest = () => {
    if (!bestNetwork || !sheet) return;
    setSheet(s => s ? { ...s, bssid: bestNetwork.BSSID, ssid: bestNetwork.SSID } : s);
  };

  return (
    <View style={styles.root}>
      {/* Map */}
      <FloorPlanMap
        floorPlanUrl={floorPlanUrl}
        aps={serverAps}
        grid={grid}
        scalePxPerM={scalePxPerM}
        onTap={openSheet}
      />

      {/* Tap hint */}
      <View style={styles.hint} pointerEvents="none">
        <Text style={styles.hintText}>TAP MAP TO PLACE AP</Text>
      </View>

      {/* Toast overlay */}
      <View style={styles.toastWrap} pointerEvents="none">
        {toasts.map(t => (
          <View
            key={t.id}
            style={[
              styles.toast,
              t.type === 'success' && styles.toastSuccess,
              t.type === 'error'   && styles.toastError,
            ]}
          >
            <Text style={styles.toastText}>{t.msg}</Text>
          </View>
        ))}
      </View>

      {/* Placement sheet */}
      <Modal
        visible={!!sheet}
        transparent
        animationType="slide"
        onRequestClose={closeSheet}
      >
        <View style={styles.overlay}>
          <View style={styles.bottomSheet}>
            {/* Handle bar */}
            <View style={styles.handle} />

            <View style={styles.sheetHeader}>
              <Text style={styles.sheetTitle}>Place Access Point</Text>
              {sheet && (
                <Text style={styles.sheetCoords}>
                  ({sheet.xM.toFixed(2)}m, {sheet.yM.toFixed(2)}m)
                </Text>
              )}
            </View>

            <ScrollView showsVerticalScrollIndicator={false}>
              {/* Auto-fill from scan */}
              {bestNetwork && (
                <TouchableOpacity style={styles.autofillBtn} onPress={fillBest}>
                  <Text style={styles.autofillText}>
                    Use strongest: {bestNetwork.BSSID}  ({bestNetwork.level} dBm)
                  </Text>
                </TouchableOpacity>
              )}

              <Field label="BSSID" value={sheet?.bssid ?? ''} onChange={v => setSheet(s => s ? { ...s, bssid: v } : s)} />
              <Field label="SSID" value={sheet?.ssid ?? ''} onChange={v => setSheet(s => s ? { ...s, ssid: v } : s)} />

              <View style={styles.row}>
                <View style={{ flex: 1, marginRight: 8 }}>
                  <Field label="RSSI REF (dBm)" value={sheet?.rssiRef ?? ''} onChange={v => setSheet(s => s ? { ...s, rssiRef: v } : s)} keyboardType="numeric" />
                </View>
                <View style={{ flex: 1 }}>
                  <Field label="PATH LOSS N" value={sheet?.pathLossN ?? ''} onChange={v => setSheet(s => s ? { ...s, pathLossN: v } : s)} keyboardType="decimal-pad" />
                </View>
              </View>

              <Field label="CEILING HEIGHT (m)" value={sheet?.ceilingH ?? ''} onChange={v => setSheet(s => s ? { ...s, ceilingH: v } : s)} keyboardType="decimal-pad" />
            </ScrollView>

            <View style={styles.sheetActions}>
              <TouchableOpacity style={styles.cancelBtn} onPress={closeSheet}>
                <Text style={styles.cancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.placeBtn, saving && { opacity: 0.6 }]}
                onPress={handlePlace}
                disabled={saving}
              >
                {saving
                  ? <ActivityIndicator size={16} color="white" />
                  : <Text style={styles.placeText}>Place AP</Text>
                }
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },

  hint: {
    position: 'absolute', bottom: 16, alignSelf: 'center',
    backgroundColor: 'rgba(0,0,0,0.6)', borderRadius: 20, borderWidth: 1, borderColor: C.border,
    paddingHorizontal: 14, paddingVertical: 6,
  },
  hintText: { fontSize: 10, color: C.textDim, fontFamily: F.mono, letterSpacing: 1.5 },

  toastWrap: {
    position: 'absolute', top: 12, left: 16, right: 16, gap: 6,
  },
  toast: {
    backgroundColor: '#1a2030', borderRadius: 10, borderWidth: 1, borderColor: C.border,
    paddingHorizontal: 14, paddingVertical: 10,
  },
  toastSuccess: { borderColor: C.green + '60', backgroundColor: '#0a1f14' },
  toastError:   { borderColor: C.red + '60',   backgroundColor: '#1f0a0a' },
  toastText:    { color: C.text, fontSize: 13 },

  overlay: {
    flex: 1, justifyContent: 'flex-end',
    backgroundColor: 'rgba(0,0,0,0.6)',
  },
  bottomSheet: {
    backgroundColor: '#0d1117',
    borderTopLeftRadius: 20, borderTopRightRadius: 20,
    borderWidth: 1, borderColor: C.border,
    paddingHorizontal: 20, paddingBottom: 36, paddingTop: 10,
    maxHeight: '85%',
  },
  handle: {
    width: 40, height: 4, borderRadius: 2,
    backgroundColor: C.border, alignSelf: 'center', marginBottom: 16,
  },
  sheetHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 },
  sheetTitle: { fontSize: 16, fontWeight: '600', color: C.text },
  sheetCoords: { fontSize: 11, color: C.textDim, fontFamily: F.mono },

  autofillBtn: {
    backgroundColor: C.primary + '18', borderRadius: S.md, borderWidth: 1, borderColor: C.primary + '40',
    padding: 10, marginBottom: 14,
  },
  autofillText: { fontSize: 11, color: C.primary, fontFamily: F.mono },

  row: { flexDirection: 'row' },

  sheetActions: { flexDirection: 'row', gap: 12, marginTop: 16 },
  cancelBtn: {
    flex: 1, padding: 14, borderRadius: S.md,
    backgroundColor: '#1a2030', borderWidth: 1, borderColor: C.border,
    alignItems: 'center',
  },
  cancelText: { color: C.textDim, fontSize: 14, fontWeight: '500' },
  placeBtn: {
    flex: 2, padding: 14, borderRadius: S.md,
    backgroundColor: C.primary, alignItems: 'center',
  },
  placeText: { color: 'white', fontSize: 14, fontWeight: '600' },
});
