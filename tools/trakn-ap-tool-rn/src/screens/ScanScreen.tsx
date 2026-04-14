import React, { useMemo } from 'react';
import {
  View, Text, FlatList, TouchableOpacity,
  StyleSheet, ActivityIndicator, RefreshControl,
} from 'react-native';
import { useStore } from '../store';
import { useWifiScan } from '../hooks/useWifiScan';
import { C, S, F } from '../theme';

function RssiBar({ level }: { level: number }) {
  // -30 best, -90 worst
  const pct = Math.max(0, Math.min(1, (level + 90) / 60));
  const bars = Math.round(pct * 4);
  const color = pct > 0.66 ? C.green : pct > 0.33 ? C.yellow : C.red;
  return (
    <View style={styles.rssiBarWrap}>
      {[0, 1, 2, 3].map(i => (
        <View
          key={i}
          style={[
            styles.rssiBarSegment,
            { height: 6 + i * 4 },
            i < bars ? { backgroundColor: color } : { backgroundColor: 'rgba(255,255,255,0.1)' },
          ]}
        />
      ))}
    </View>
  );
}

function SignalBadge({ level }: { level: number }) {
  const pct = (level + 90) / 60;
  const color = pct > 0.66 ? C.green : pct > 0.33 ? C.yellow : C.red;
  return (
    <View style={[styles.signalBadge, { borderColor: color + '40', backgroundColor: color + '18' }]}>
      <Text style={[styles.signalText, { color }]}>{level} dBm</Text>
    </View>
  );
}

export default function ScanScreen() {
  const { rescan } = useWifiScan();
  const networks   = useStore(s => s.networks);
  const bestAp     = useStore(s => s.bestAp);
  const isScanning = useStore(s => s.isScanning);
  const serverAps  = useStore(s => s.serverAps);
  const lastScanTs = useStore(s => s.lastScanTs);

  const placedBssids = useMemo(
    () => new Set(serverAps.map(a => a.bssid.toLowerCase())),
    [serverAps],
  );

  return (
    <View style={styles.root}>
      {/* Best AP Banner */}
      {bestAp ? (
        <View style={styles.banner}>
          <View style={styles.bannerLeft}>
            <Text style={styles.bannerLabel}>STRONGEST SIGNAL</Text>
            <Text style={styles.bannerBssid}>{bestAp.BSSID}</Text>
            <Text style={styles.bannerSsid}>{bestAp.SSID}</Text>
          </View>
          <View style={styles.bannerRight}>
            <RssiBar level={bestAp.level} />
            <Text style={styles.bannerDbm}>{bestAp.level} dBm</Text>
          </View>
        </View>
      ) : (
        <View style={styles.banner}>
          <Text style={{ color: C.textDim, fontSize: 13 }}>
            {isScanning ? 'Scanning...' : 'No networks found'}
          </Text>
        </View>
      )}

      {/* Scan info row */}
      <View style={styles.infoRow}>
        <Text style={styles.infoText}>
          {networks.length} network{networks.length !== 1 ? 's' : ''} found
          {lastScanTs ? `  •  ${lastScanTs}` : ''}
        </Text>
        <TouchableOpacity onPress={rescan} disabled={isScanning} style={styles.rescanBtn}>
          {isScanning
            ? <ActivityIndicator size={14} color={C.primary} />
            : <Text style={styles.rescanText}>Rescan</Text>
          }
        </TouchableOpacity>
      </View>

      {/* Network list */}
      <FlatList
        data={networks}
        keyExtractor={item => item.BSSID}
        contentContainerStyle={{ paddingHorizontal: 12, paddingBottom: 24 }}
        refreshControl={
          <RefreshControl refreshing={isScanning} onRefresh={rescan} tintColor={C.primary} />
        }
        renderItem={({ item }) => {
          const placed = placedBssids.has(item.BSSID.toLowerCase());
          return (
            <View style={[styles.card, placed && styles.cardPlaced]}>
              <View style={styles.cardLeft}>
                <View style={styles.cardHeader}>
                  <Text style={styles.bssid}>{item.BSSID}</Text>
                  {placed && (
                    <View style={styles.placedTag}>
                      <Text style={styles.placedTagText}>PLACED</Text>
                    </View>
                  )}
                </View>
                <Text style={styles.ssid}>{item.SSID || '(hidden)'}</Text>
                <Text style={styles.freq}>{item.frequency >= 5000 ? '5 GHz' : '2.4 GHz'}</Text>
              </View>
              <View style={styles.cardRight}>
                <RssiBar level={item.level} />
                <SignalBadge level={item.level} />
              </View>
            </View>
          );
        }}
        ListEmptyComponent={
          !isScanning ? (
            <View style={styles.empty}>
              <Text style={styles.emptyText}>No networks detected</Text>
              <Text style={styles.emptySubtext}>Ensure location permission is granted</Text>
            </View>
          ) : null
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },

  banner: {
    margin: 12,
    padding: 14,
    backgroundColor: '#0d1117',
    borderRadius: S.lg,
    borderWidth: 1,
    borderColor: C.border,
    flexDirection: 'row',
    alignItems: 'center',
  },
  bannerLeft: { flex: 1 },
  bannerRight: { alignItems: 'flex-end', gap: 4 },
  bannerLabel: { fontSize: 9, color: C.primary, fontFamily: F.mono, letterSpacing: 1.5, marginBottom: 4 },
  bannerBssid: { fontSize: 13, color: C.text, fontFamily: F.mono, fontWeight: '600' },
  bannerSsid: { fontSize: 11, color: C.textDim, marginTop: 2 },
  bannerDbm: { fontSize: 11, color: C.textDim, fontFamily: F.mono, marginTop: 2 },

  rssiBarWrap: { flexDirection: 'row', alignItems: 'flex-end', gap: 2 },
  rssiBarSegment: { width: 5, borderRadius: 2 },

  signalBadge: { borderRadius: 6, borderWidth: 1, paddingHorizontal: 7, paddingVertical: 2 },
  signalText: { fontSize: 10, fontFamily: F.mono, fontWeight: '600' },

  infoRow: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingBottom: 8,
  },
  infoText: { fontSize: 11, color: C.textDim, fontFamily: F.mono },
  rescanBtn: {
    paddingHorizontal: 12, paddingVertical: 5,
    backgroundColor: '#1a2030', borderRadius: 8,
    borderWidth: 1, borderColor: C.border,
    minWidth: 64, alignItems: 'center',
  },
  rescanText: { fontSize: 12, color: C.primary, fontWeight: '500' },

  card: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: '#0d1117',
    borderRadius: S.lg, borderWidth: 1, borderColor: C.border,
    padding: 12, marginBottom: 8,
  },
  cardPlaced: { borderColor: C.primary + '50', backgroundColor: '#0f0e16' },
  cardLeft: { flex: 1 },
  cardRight: { alignItems: 'flex-end', gap: 6 },
  cardHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 2 },
  bssid: { fontSize: 12, color: C.text, fontFamily: F.mono },
  ssid: { fontSize: 12, color: C.textDim },
  freq: { fontSize: 10, color: C.textDim + 'aa', marginTop: 2, fontFamily: F.mono },
  placedTag: {
    backgroundColor: C.primary + '25', borderRadius: 4, borderWidth: 1, borderColor: C.primary + '60',
    paddingHorizontal: 5, paddingVertical: 1,
  },
  placedTagText: { fontSize: 8, color: C.primary, fontFamily: F.mono, letterSpacing: 1 },

  empty: { alignItems: 'center', paddingTop: 60 },
  emptyText: { color: C.textDim, fontSize: 14, fontWeight: '500' },
  emptySubtext: { color: C.textDim + '88', fontSize: 12, marginTop: 6 },
});
