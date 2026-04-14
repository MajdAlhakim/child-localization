import 'react-native-gesture-handler';
import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { StatusBar } from 'expo-status-bar';
import { StyleSheet } from 'react-native';
import AppNavigator from './navigation/AppNavigator';
import { C } from './theme';

export default function App() {
  return (
    <GestureHandlerRootView style={styles.root}>
      <StatusBar style="light" backgroundColor={C.bg} />
      <NavigationContainer
        theme={{
          dark: true,
          colors: {
            primary: C.primary,
            background: C.bg,
            card: '#0a0e16',
            text: C.text,
            border: C.border,
            notification: C.primary,
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
