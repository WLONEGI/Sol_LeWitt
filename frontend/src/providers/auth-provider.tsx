"use client"

import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react"
import type { FirebaseError } from "firebase/app"
import {
    onIdTokenChanged,
    signInWithPopup,
    signInWithRedirect,
    getRedirectResult,
    signOut,
} from "firebase/auth"
import type { User } from "firebase/auth"
import { auth, googleProvider } from "@/lib/firebase/client"
import { useChatStore } from "@/features/chat/stores/chat"

interface AuthContextValue {
    user: User | null
    token: string | null
    loading: boolean
    error: string | null
    signInWithGoogle: () => Promise<void>
    signOutUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

const toFirebaseError = (error: unknown): FirebaseError | null => {
    if (typeof error === "object" && error !== null && "code" in error) {
        return error as FirebaseError
    }
    return null
}

const getAuthErrorMessage = (code?: string, fallback?: string) => {
    switch (code) {
        case "auth/popup-closed-by-user":
            return "ログインがキャンセルされました"
        case "auth/cancelled-popup-request":
            return "ログイン処理が中断されました。もう一度お試しください"
        case "auth/popup-blocked":
            return "ポップアップがブロックされました。ブラウザ設定をご確認ください"
        case "auth/network-request-failed":
            return "ネットワークエラーが発生しました。接続を確認してください"
        default:
            return fallback || "ログインに失敗しました"
    }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [user, setUser] = useState<User | null>(null)
    const [token, setToken] = useState<string | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const previousUidRef = useRef<string | null>(null)
    const bypassAuthForE2E = process.env.NEXT_PUBLIC_E2E_BYPASS_AUTH === "1"

    useEffect(() => {
        if (bypassAuthForE2E) {
            const mockUser = {
                uid: "e2e-user",
                displayName: "E2E User",
                email: "e2e@example.com",
            } as User
            previousUidRef.current = mockUser.uid
            setUser(mockUser)
            setToken("e2e-test-token")
            setError(null)
            setLoading(false)
            return
        }

        const unsubscribe = onIdTokenChanged(auth, async (nextUser) => {
            const nextUid = nextUser?.uid ?? null
            if (previousUidRef.current !== nextUid) {
                useChatStore.getState().resetForAuthBoundary()
                previousUidRef.current = nextUid
            }
            setUser(nextUser)
            if (nextUser) {
                try {
                    const nextToken = await nextUser.getIdToken()
                    setToken(nextToken)
                } catch (error: unknown) {
                    const authError = toFirebaseError(error)
                    setToken(null)
                    setError(getAuthErrorMessage(authError?.code, authError?.message))
                }
            } else {
                setToken(null)
            }
            setLoading(false)
        })

        getRedirectResult(auth)
            .then(() => {
                setError(null)
            })
            .catch((error: unknown) => {
                const authError = toFirebaseError(error)
                if (authError) {
                    setError(getAuthErrorMessage(authError.code, authError.message))
                }
            })

        return () => unsubscribe()
    }, [bypassAuthForE2E])

    const signInWithGoogle = async () => {
        if (bypassAuthForE2E) {
            return
        }
        setError(null)
        try {
            await signInWithPopup(auth, googleProvider)
        } catch (error: unknown) {
            const authError = toFirebaseError(error)
            const code = authError?.code
            if (code === "auth/operation-not-supported-in-this-environment") {
                try {
                    await signInWithRedirect(auth, googleProvider)
                } catch (redirectError: unknown) {
                    const redirectAuthError = toFirebaseError(redirectError)
                    setError(getAuthErrorMessage(redirectAuthError?.code, redirectAuthError?.message))
                }
                return
            }
            setError(getAuthErrorMessage(code, authError?.message))
        }
    }

    const signOutUser = async () => {
        if (bypassAuthForE2E) {
            setUser(null)
            setToken(null)
            return
        }
        try {
            await signOut(auth)
        } catch (error: unknown) {
            const authError = toFirebaseError(error)
            setError(getAuthErrorMessage(authError?.code, authError?.message))
        }
    }

    const value = useMemo(
        () => ({ user, token, loading, error, signInWithGoogle, signOutUser }),
        [user, token, loading, error]
    )

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
    const ctx = useContext(AuthContext)
    if (!ctx) {
        throw new Error("useAuth must be used within AuthProvider")
    }
    return ctx
}
