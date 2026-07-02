// Tiny custom navigator: two tabs (Home / Transactions) + a prominent center
// Add FAB that opens the Quick Add modal. Settings and the recurring-commitments
// manager are full-screen overlays reached from the header / Home. The selected
// month is held here so Home and Transactions stay in sync. The transaction
// editor lives here too so edits/deletes from either screen refresh both.
import { Ionicons } from '@expo/vector-icons';
import React, { useState } from 'react';
import { Modal, Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { TransactionEditor } from './components/transactions/TransactionEditor';
import { AppText } from './components/ui';
import { MenuSheet } from './components/ui/MenuSheet';
import { currentMonth } from './format';
import { GoalsScreen } from './screens/GoalsScreen';
import { HomeScreen } from './screens/HomeScreen';
import { QuickAddScreen } from './screens/QuickAddScreen';
import { RecurringScreen } from './screens/RecurringScreen';
import { SettingsScreen } from './screens/SettingsScreen';
import { TransactionsScreen } from './screens/TransactionsScreen';
import { colors, font, radius, shadow, spacing, weight } from './theme';

type Tab = 'home' | 'transactions';

export function RootNavigator() {
  const insets = useSafeAreaInsets();
  const [tab, setTab] = useState<Tab>('home');
  const [month, setMonth] = useState(currentMonth());
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [recurringOpen, setRecurringOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [goalsOpen, setGoalsOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [addSession, setAddSession] = useState(0); // bump to remount a fresh form
  const [editTxnId, setEditTxnId] = useState<string | null>(null);
  const [dataVersion, setDataVersion] = useState(0);

  const openAdd = () => {
    setAddSession((s) => s + 1);
    setAddOpen(true);
  };
  const bumpData = () => setDataVersion((v) => v + 1);
  const onAdded = () => {
    setAddOpen(false);
    bumpData();
  };
  const afterEdit = () => {
    setEditTxnId(null);
    bumpData();
  };

  const overlay = settingsOpen || recurringOpen || goalsOpen;

  return (
    <View style={styles.flex}>
      <View style={styles.flex}>
        {settingsOpen ? (
          <SettingsScreen onBack={() => setSettingsOpen(false)} />
        ) : recurringOpen ? (
          <RecurringScreen onBack={() => setRecurringOpen(false)} onChanged={bumpData} />
        ) : goalsOpen ? (
          <GoalsScreen month={month} onBack={() => setGoalsOpen(false)} onChanged={bumpData} />
        ) : tab === 'home' ? (
          <HomeScreen
            dataVersion={dataVersion}
            month={month}
            onMonthChange={setMonth}
            onQuickAdd={openAdd}
            onOpenMenu={() => setMenuOpen(true)}
            onOpenRecurring={() => setRecurringOpen(true)}
            onOpenGoal={() => setGoalsOpen(true)}
            onEditTransaction={setEditTxnId}
          />
        ) : (
          <TransactionsScreen
            dataVersion={dataVersion}
            month={month}
            onMonthChange={setMonth}
            onOpenMenu={() => setMenuOpen(true)}
            onEditTransaction={setEditTxnId}
          />
        )}
      </View>

      {/* Bottom tab bar + center Add FAB (hidden under full-screen overlays) */}
      {!overlay ? (
        <View style={[styles.tabBar, { paddingBottom: insets.bottom + spacing.xs }]}>
          <TabButton label="בית" icon="home" active={tab === 'home'} onPress={() => setTab('home')} />
          <Pressable onPress={openAdd} style={styles.fab}>
            <Ionicons name="add" size={30} color={colors.onAccent} />
          </Pressable>
          <TabButton
            label="עסקאות"
            icon="receipt"
            active={tab === 'transactions'}
            onPress={() => setTab('transactions')}
          />
        </View>
      ) : null}

      <Modal
        visible={addOpen}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setAddOpen(false)}
      >
        <QuickAddScreen key={addSession} onClose={() => setAddOpen(false)} onAdded={onAdded} />
      </Modal>

      <TransactionEditor
        txnId={editTxnId}
        visible={editTxnId !== null}
        onClose={() => setEditTxnId(null)}
        onSaved={afterEdit}
        onDeleted={afterEdit}
      />

      <MenuSheet
        visible={menuOpen}
        onClose={() => setMenuOpen(false)}
        onHome={() => { setTab('home'); setSettingsOpen(false); setRecurringOpen(false); }}
        onRecurring={() => setRecurringOpen(true)}
        onGoal={() => setGoalsOpen(true)}
        onSettings={() => setSettingsOpen(true)}
      />

    </View>
  );
}

function TabButton({
  label,
  icon,
  active,
  onPress,
}: {
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  active: boolean;
  onPress: () => void;
}) {
  const color = active ? colors.accent : colors.textMuted;
  return (
    <Pressable onPress={onPress} style={styles.tab} hitSlop={8}>
      <Ionicons name={active ? icon : (`${icon}-outline` as keyof typeof Ionicons.glyphMap)} size={24} color={color} />
      <AppText size={font.micro} color={color} weight={active ? weight.semibold : weight.regular}>
        {label}
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.bg },
  tabBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-around',
    paddingTop: spacing.sm,
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  tab: { alignItems: 'center', gap: 2, flex: 1, paddingVertical: spacing.xs },
  fab: {
    width: 60,
    height: 60,
    borderRadius: radius.pill,
    backgroundColor: colors.accent,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: -28,
    ...shadow,
  },
});
