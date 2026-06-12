import { collection, doc, getFirestore, onSnapshot, type Unsubscribe } from 'firebase/firestore'

import { getFirebaseApp, initializeFirebaseClient } from '@/services/firebase'

export interface WorkOrderLockDoc {
  holderUid: string
  holderEmail?: string
  acquiredAt?: string
  sessionId?: string
}

export interface TeamWorkOrderSnapshot {
  id: string
  data: Record<string, unknown>
}

export async function subscribeTeamWorkOrders(
  orgId: string,
  onChange: (items: TeamWorkOrderSnapshot[]) => void
): Promise<Unsubscribe> {
  await initializeFirebaseClient()
  const ref = collection(getFirestore(getFirebaseApp()), 'organizations', orgId, 'workOrders')
  return onSnapshot(ref, snapshot => {
    onChange(snapshot.docs.map(docSnap => ({ id: docSnap.id, data: docSnap.data() as Record<string, unknown> })))
  })
}

export async function subscribeWorkOrderLock(
  orgId: string,
  workOrderId: string,
  onChange: (lock: WorkOrderLockDoc | null) => void
): Promise<Unsubscribe> {
  await initializeFirebaseClient()
  const ref = doc(getFirestore(getFirebaseApp()), 'organizations', orgId, 'locks', workOrderId)
  return onSnapshot(ref, snapshot => {
    onChange(snapshot.exists() ? (snapshot.data() as WorkOrderLockDoc) : null)
  })
}
