import type { FirebaseWebConfig } from '@/lib/firebase-config'

/**
 * Public Firebase web client config for the LivingColor cloud project.
 *
 * Safe to commit: Firebase apiKey is not a secret (security is enforced by
 * Auth + Firestore rules + App Check). Never put the service-account JSON here.
 */
export const LIVINGCOLOR_CLOUD_FIREBASE_CONFIG: FirebaseWebConfig = {
  apiKey: 'AIzaSyA_FP7bRS4aZHnZO09BjBJ2WdSN5igU3oM',
  authDomain: 'livingcolor-app.firebaseapp.com',
  projectId: 'livingcolor-app',
  storageBucket: 'livingcolor-app.firebasestorage.app',
  messagingSenderId: '1060766035569',
  appId: '1:1060766035569:web:3633d544de759f83c6f5d0'
}
