import React, { useState, useCallback } from 'react';
import {
  View, Text, FlatList, TouchableOpacity,
  StyleSheet, ActivityIndicator, Alert, RefreshControl,
} from 'react-native';
import { useStore } from '../store';
import { apApi, checkHealth } from '../api/client';
import { C, S, F } from '../theme';
import { useToastState } from '../hooks/useToast';
import type { ApEntry } from '../api/client';

function ApCard({ ap, onDelete }: { ap: ApEntry; onDelete: (bssid: string) => void }) {
  return (
    <View style={styles.card}>
      <View style={styles.cardBody}>
        <View style={styles.cardLeft}>
          <Text style={styles.bssid}>{ap.bssid}</Text>
          <Text style={styles.ssid}>{ap.ssid || '(no SSID)'}</Text>
          <Text style={styles.coords}>
            x={ap.x.toFixed(2)}m  y={ap.y.toFixed(2)}m  h={ap.ceiling_height.toFixed(1)}m
          </Text>
        </View>
        <View style={styles.cardRight}>
          <View style={styles.paramRow}>
            <Text style={styles.paramLabel}>REF</Text>
            <Text style={styles.paramVal}>{ap.rssi_ref} dBm</Text>
          </View>
          <View style={styles.paramRow}>
            <Text style={styles.paramLabel}>N</Text>
            <Text style={styles.paramVal}>{ap.path_loss_n}</Text>
          </View>
          <TouchableOpacity
            style={styles.deleteBtn}
            onPress={() => onDelete(ap.bssid)}
          >
            <Text style={styles.deleteBtnText}>Delete</Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

export default function StatusScreen() {
  const isOnline   = useStore(s => s.isOnline);
  const setOnline  = useStore(s => s.setOnline);
  const serverAps  = useStore(s => s.serverAps);
  const setServerAps = useStore(s => s.setServerAps);
  const [loading, setLoading] = useState(false);
  const { toasts, toast } = useToastState();

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [online, apsRes] = await Promise.all([
        checkHealth(),
        apApi.list().catch(() => null),
      ]);
      setOnline(online);
      if (apsRes) setServerAps(apsRes.access_points);
    } finally {
      setLoading(false);
    }
  }, [setOnline, setServerAps]);

  React.useEffect(() => { refresh(); }, []);

  const handleDeleteOne = (bssid: string) => {
    Alert.alert(
      'Delete AP',
      `Remove ${bssid}?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete', style: 'destructive',
          onPress: async () => {
            try {
              await apApi.deleteOne(bssid);
              toast('AP removed', 'success');
              await refresh();
            } catch {
              toast('Failed to delete AP', 'error');
            }
          },
        },
      ],
    );
  };

  const handleDeleteAll = () => {
    Alert.alert(
      'Clear All APs',
      `Remove all ${serverAps.length} access points from the venue?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Clear All', style: 'destructive',
          onPress: async () => {
            try {
              await apApi.deleteAll();
              toast('All APs removed', 'success');
              await refresh();
            } catch {
              toast('Failed to clear APs', 'error');
            }
          },
        },
      ],
    );
  };

  return (
    <View style={styles.root}>
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

      {/* Status cards */}
      <View style={styles.statsRow}>
        <View style={[styles.statCard, { flex: 1 }]}>
          <View style={[styles.indicator, { backgroundColor: isOnline ? C.green : C.red }]} />
          <Text style={styles.statLabel}>SERVER</Text>
          <Text style={[styles.statValue, { color: isOnline ? C.green : C.red }]}>
            {isOnline ? 'Online' : 'Offline'}
          </Text>
        </View>
        <View style={[styles.statCard, { flex: 1 }]}>
          <Text style={styles.statLabel}>PLACED APs</Text>
          <Text style={[styles.statValue, { color: C.primary }]}>{serverAps.length}</Text>
        </View>
        <TouchableOpacity
          style={[styles.statCard, { flex: 1 }]}
          onPress={refresh}
          disabled={loading}
        >
          {loading
            ? <ActivityIndicator size={20} color={C.primary} />
            : <Text style={[styles.statValue, { color: C.primary }]}>Refresh</Text>
          }
        </TouchableOpacity>
      </View>

      {/* Delete all button */}
      {serverAps.length > 0 && (
        <TouchableOpacity style={styles.clearAllBtn} onPress={handleDeleteAll}>
          <Text style={styles.clearAllText}>Clear All APs</Text>
        </TouchableOpacity>
      )}

      {/* AP list */}
      <FlatList
        data={serverAps}
        keyExtractor={item => item.bssid}
        contentContainerStyle={{ paddingHorizontal: 12, paddingBottom: 24 }}
        refreshControl={
          <RefreshControl refreshing={loading} onRefresh={refresh} tintColor={C.primary} />
        }
        renderItem={({ item }) => (
          <ApCard ap={item} onDelete={handleDeleteOne} />
        )}
        ListEmptyComponent={
          !loading ? (
            <View style={styles.empty}>
              <Text style={styles.emptyText}>No access points placed</Text>
              <Text style={styles.emptySubtext}>Use the Map tab to place APs on the floor plan</Text>
            </View>
          ) : null
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },

  toastWrap: { position: 'absolute', top: 12, left: 16, right: 16, zIndex: 100, gap: 6 },
  toast: {
    backgroundColor: '#1a2030', borderRadius: 10, borderWidth: 1, borderColor: C.border,
    paddingHorizontal: 14, paddingVertical: 10,
  },
  toastSuccess: { borderColor: C.green + '60', backgroundColor: '#0a1f14' },
  toastError:   { borderColor: C.red + '60',   backgroundColor: '#1f0a0a' },
  toastText:    { color: C.text, fontSize: 13 },

  statsRow: { flexDirection: 'row', gap: 8, padding: 12 },
  statCard: {
    backgroundColor: '#0d1117', borderRadius: S.lg, borderWidth: 1, borderColor: C.border,
    padding: 14, alignItems: 'center', justifyContent: 'center', minHeight: 72,
  },
  indicator: { width: 8, height: 8, borderRadius: 4, marginBottom: 6 },
  statLabel: { fontSize: 9, color: C.textDim, fontFamily: F.mono, letterSpacing: 1.2, marginBottom: 4 },
  statValue: { fontSize: 18, fontWeight: '700', color: C.text },

  clearAllBtn: {
    marginHorizontal: 12, marginBottom: 8,
    padding: 12, borderRadius: S.md,
    backgroundColor: '#1f0a0a', borderWidth: 1, borderColor: C.red + '50',
    alignItems: 'center',
  },
  clearAllText: { color: C.red, fontSize: 13, fontWeight: '500' },

  card: {
    backgroundColor: '#0d1117', borderRadius: S.lg, borderWidth: 1, borderColor: C.border,
    marginBottom: 8, overflow: 'hidden',
  },
  cardBody: { flexDirection: 'row', padding: 12 },
  cardLeft: { flex: 1 },
  cardRight: { alignItems: 'flex-end', gap: 4 },
  bssid: { fontSize: 12, color: C.text, fontFamily: F.mono, fontWeight: '600' },
  ssid: { fontSize: 12, color: C.textDim, marginTop: 2 },
  coords: { fontSize: 10, color: C.textDim + 'aa', fontFamily: F.mono, marginTop: 4 },

  paramRow: { flexDirection: 'row', gap: 4, alignItems: 'center' },
  paramLabel: { fontSize: 9, color: C.textDim, fontFamily: F.mono, letterSpacing: 1 },
  paramVal: { fontSize: 10, color: C.text, fontFamily: F.mono },

  deleteBtn: {
    marginTop: 6, paddingHorizontal: 10, paddingVertical: 4,
    backgroundColor: C.red + '18', borderRadius: 6, borderWidth: 1, borderColor: C.red + '40',
  },
  deleteBtnText: { fontSize: 11, color: C.red },

  empty: { alignItems: 'center', paddingTop: 60 },
  emptyText: { color: C.textDim, fontSize: 14, fontWeight: '500' },
  emptySubtext: { color: C.textDim + '88', fontSize: 12, marginTop: 6, textAlign: 'center', paddingHorizontal: 24 },
});
