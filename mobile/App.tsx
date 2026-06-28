// Root: forces Hebrew RTL, then routes between the dev token gate and Home.
// No navigation library — a single screen plus the gate is all this slice needs.
import { StatusBar } from 'expo-status-bar';
import React, { useEffect, useState } from 'react';
import { I18nManager, SafeAreaView, StyleSheet } from 'react-native';

import { clearToken, getToken } from './src/api';
import { Loading } from './src/components/ui';
import HomeScreen from './src/screens/HomeScreen';
import TokenGateScreen from './src/screens/TokenGateScreen';
import { colors } from './src/theme';

// Hebrew-first: lay everything out right-to-left.
I18nManager.allowRTL(true);
I18nManager.forceRTL(true);

type Route = 'loading' | 'gate' | 'home';

export default function App() {
  const [route, setRoute] = useState<Route>('loading');

  useEffect(() => {
    getToken().then((t) => setRoute(t ? 'home' : 'gate'));
  }, []);

  async function onAuthExpired() {
    await clearToken();
    setRoute('gate');
  }

  return (
    <SafeAreaView style={styles.root}>
      <StatusBar style="light" />
      {route === 'loading' ? <Loading /> : null}
      {route === 'gate' ? <TokenGateScreen onReady={() => setRoute('home')} /> : null}
      {route === 'home' ? <HomeScreen onAuthExpired={onAuthExpired} /> : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
});
