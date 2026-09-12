import React, { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import { ConnectionContext, ConnectionGuard } from './ConnectionGuard';
import { LoadingState, Screen } from './components/ui';
import { RootNavigator } from './RootNavigator';
import { ConnectionScreen } from './screens/ConnectionScreen';
import { session } from './session';

const renderGate = () => <ConnectionScreen />;

export function SessionGate() {
  const state = useSyncExternalStore(session.subscribe, session.getSnapshot, session.getSnapshot);
  const [covers, setCovers] = useState<string[]>([]);
  const registerCover = useCallback((id: string) => {
    setCovers((current) => [...current, id]);
    return () => { setCovers((current) => current.filter((item) => item !== id)); };
  }, []);
  useEffect(() => { void session.restore(); }, []);
  if (state.status === 'loading') return <Screen><LoadingState label="פותח את החיבור השמור…" /></Screen>;
  if (state.status === 'disconnected') return <ConnectionScreen />;
  return (
    <ConnectionContext.Provider value={{ locked: state.status === 'expired', renderGate, registerCover, topCover: covers[covers.length - 1] ?? null }}>
      <ConnectionGuard><RootNavigator connectionVersion={state.version} /></ConnectionGuard>
    </ConnectionContext.Provider>
  );
}
