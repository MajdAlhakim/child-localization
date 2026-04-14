import 'react-native-gesture-handler';
import React, { useEffect } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { StatusBar } from 'expo-status-bar';
import { StyleSheet } from 'react-native';
import AppNavigator from './navigation/AppNavigator';
import { useStore } from './store';
import { checkHealth, apApi, gridApi } from './api/client';

export default function App() {
  const setOnline    = useStore(s => s.setOnline);
  const setServerAps = useStore(s => s.setServerAps);
  const setGrid      = useStore(s => s.setGrid);

  // Bootstrap: health check + load server state
  useEffect(() => {
    const boot = async () => {
      const online = await checkHealth();
      setOnline(online);
      if (online) {
        const [apsRes, gridRes] = await Promise.all([
          apApi.list().catch(() => null),
          gridApi.get().catch(() => null),
        ]);
        if (apsRes) setServerAps(apsRes.access_points);
        if (gridRes) setGrid(gridRes);
      }
    };
    boot();
  }, []);

  return (
    <GestureHandlerRootView style={styles.root}>
      <StatusBar style="light" backgroundColor="#060a10" />
      <NavigationContainer
        theme={{
          dark: true,
          colors: {
            primary: '#f97316',
            background: '#060a10',
            card: '#0a0e16',
            text: '#e2e8f0',
            border: '#1a2030',
            notification: '#f97316',
          },
        }}
      >
        <AppNavigator />
      </NavigationContainer>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
});
