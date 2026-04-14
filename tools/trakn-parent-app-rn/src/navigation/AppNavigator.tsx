import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { useStore } from '../store';
import { C, F } from '../theme';
import LocateScreen   from '../screens/LocateScreen';
import SettingsScreen from '../screens/SettingsScreen';

const Tab = createBottomTabNavigator();

function LocateIcon({ focused }: { focused: boolean }) {
  const col = focused ? C.primary : C.textDim;
  return (
    <View style={icon.wrap}>
      <View style={[icon.outer, { borderColor: col }]}>
        <View style={[icon.inner, { backgroundColor: col }]} />
      </View>
      {/* Crosshair lines */}
      <View style={[icon.lineH, { backgroundColor: col }]} />
      <View style={[icon.lineV, { backgroundColor: col }]} />
    </View>
  );
}

function SettingsIcon({ focused }: { focused: boolean }) {
  const col = focused ? C.primary : C.textDim;
  return (
    <View style={icon.wrap}>
      <View style={[icon.gearOuter, { borderColor: col }]}>
        <View style={[icon.gearInner, { backgroundColor: col }]} />
      </View>
    </View>
  );
}

const icon = StyleSheet.create({
  wrap: { width: 24, height: 24, alignItems: 'center', justifyContent: 'center' },
  outer: { width: 18, height: 18, borderRadius: 9, borderWidth: 1.5 , alignItems: 'center', justifyContent: 'center' },
  inner: { width: 6, height: 6, borderRadius: 3 },
  lineH: { position: 'absolute', width: 24, height: 1.5, top: '50%' },
  lineV: { position: 'absolute', width: 1.5, height: 24, left: '50%' },
  gearOuter: { width: 18, height: 18, borderRadius: 9, borderWidth: 2, alignItems: 'center', justifyContent: 'center' },
  gearInner: { width: 6, height: 6, borderRadius: 3 },
});

export default function AppNavigator() {
  const isOnline       = useStore(s => s.isOnline);
  const trackingActive = useStore(s => s.trackingActive);
  const position       = useStore(s => s.position);

  return (
    <Tab.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: '#0a0e16', borderBottomWidth: 1, borderBottomColor: '#1a2030' },
        headerTitleStyle: { color: C.text, fontSize: 15, fontWeight: '600', fontFamily: F.mono },
        tabBarStyle: {
          backgroundColor: '#0a0e16',
          borderTopWidth: 1,
          borderTopColor: '#1a2030',
          height: 60,
          paddingBottom: 8,
        },
        tabBarActiveTintColor:   C.primary,
        tabBarInactiveTintColor: C.textDim,
        tabBarLabelStyle: { fontSize: 10, fontFamily: F.mono, letterSpacing: 0.5 },
      }}
    >
      <Tab.Screen
        name="Locate"
        component={LocateScreen}
        options={{
          title: 'TRAKN',
          tabBarLabel: 'Locate',
          tabBarIcon: ({ focused }) => <LocateIcon focused={focused} />,
          tabBarBadge: trackingActive ? ' ' : undefined,
          tabBarBadgeStyle: { backgroundColor: C.primary, minWidth: 8, height: 8, borderRadius: 4 },
          headerRight: () => (
            <View style={{ flexDirection: 'row', alignItems: 'center', marginRight: 14, gap: 6 }}>
              <View style={{ width: 7, height: 7, borderRadius: 3.5, backgroundColor: isOnline ? C.green : C.red }} />
              <Text style={{ fontSize: 11, color: isOnline ? C.green : C.red, fontFamily: F.mono }}>
                {isOnline ? 'online' : 'offline'}
              </Text>
            </View>
          ),
        }}
      />
      <Tab.Screen
        name="Settings"
        component={SettingsScreen}
        options={{
          title: 'Settings',
          tabBarLabel: 'Settings',
          tabBarIcon: ({ focused }) => <SettingsIcon focused={focused} />,
        }}
      />
    </Tab.Navigator>
  );
}
