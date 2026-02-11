"use client"

import { initializeApp, getApp, getApps } from "firebase/app"
import { getAuth, GoogleAuthProvider } from "firebase/auth"

// Firebase configuration
let firebaseConfig = {
    apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
    authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
    projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
    storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
    messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
    appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
}

// Fallback to FIREBASE_WEBAPP_CONFIG if individual variables are missing
if (!firebaseConfig.apiKey && process.env.FIREBASE_WEBAPP_CONFIG) {
    try {
        const config = JSON.parse(process.env.FIREBASE_WEBAPP_CONFIG);
        firebaseConfig = {
            apiKey: config.apiKey,
            authDomain: config.authDomain,
            projectId: config.projectId,
            storageBucket: config.storageBucket,
            messagingSenderId: config.messagingSenderId,
            appId: config.appId,
        };
    } catch (e) {
        console.error("Failed to parse FIREBASE_WEBAPP_CONFIG", e);
    }
}

const isConfigValid = !!firebaseConfig.apiKey && !!firebaseConfig.authDomain

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
    } else {
        console.warn("Firebase configuration is invalid or missing.")
    }
}

export { auth, googleProvider }
