"use client"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { useAuth } from "@/providers/auth-provider"

export function MainHeader({ className }: { className?: string }) {
    const { user, loading, error, signInWithGoogle } = useAuth()

    const handleAuthClick = async () => {
        await signInWithGoogle()
    }

    return (
        <header
            className={cn(
                "relative w-full h-12 flex items-center shrink-0 border-b-0 select-none",
                "bg-background/80 backdrop-blur-sm z-50",
                className
            )}
        >
            <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-6">
                <div className="flex items-center gap-2 text-sm font-semibold tracking-[0.2em] text-foreground">
                    Sol LeWitt
                </div>
                <div className="flex items-center justify-end gap-2">
                    {!loading && !user ? (
                        <>
                            <Button size="sm" onClick={handleAuthClick} disabled={loading}>
                                Sign in
                            </Button>
                            <Button variant="outline" size="sm" onClick={handleAuthClick} disabled={loading}>
                                Sign up
                            </Button>
                        </>
                    ) : null}
                </div>
            </div>
            {!loading && !user && error ? (
                <div className="absolute top-12 right-6 max-w-xs rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 shadow-sm">
                    {error}
                </div>
            ) : null}
        </header>
    )
}
