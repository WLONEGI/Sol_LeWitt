"use client"

import { initializeApp, getApp, getApps } from "firebase/app"
import { getAuth, GoogleAuthProvider } from "firebase/auth"

const firebaseConfig = {
    apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
    authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
    projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
    appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
}

// Build-time safety: initialize only when API key is present
const isConfigValid = !!firebaseConfig.apiKey;

let app: any;
let auth: any;
let googleProvider: any;

if (typeof window !== "undefined") {
    console.log("Firebase client.ts: Initializing...", {
        hasApiKey: !!firebaseConfig.apiKey,
        isConfigValid
    })

    if (isConfigValid) {
        app = getApps().length ? getApp() : initializeApp(firebaseConfig)
        auth = getAuth(app)
        googleProvider = new GoogleAuthProvider()
        googleProvider.setCustomParameters({ prompt: "select_account" })
    }
}

export { auth, googleProvider }
