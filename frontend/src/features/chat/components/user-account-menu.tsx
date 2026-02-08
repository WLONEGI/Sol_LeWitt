"use client"

import { useEffect, useId, useMemo, useRef, useState } from "react"
import { ChevronRight, CircleHelp, LogOut, Settings, Sparkles } from "lucide-react"

import { cn } from "@/lib/utils"
import { useAuth } from "@/providers/auth-provider"

type UserAccountMenuProps = {
    collapsed?: boolean
    placement?: "sidebar" | "header"
    className?: string
}

export function UserAccountMenu({
    collapsed = false,
    placement = "sidebar",
    className,
}: UserAccountMenuProps) {
    const { user, signOutUser, signInWithGoogle } = useAuth()
    const [isMenuOpen, setIsMenuOpen] = useState(false)
    const menuRef = useRef<HTMLDivElement | null>(null)
    const menuId = useId()

    const displayName = useMemo(() => {
        if (!user) return "User"
        return user.displayName || user.email || "User"
    }, [user])

    const displayEmail = user?.email || ""
    const avatarUrl = user?.photoURL || ""

    useEffect(() => {
        if (!isMenuOpen) return
        const handleClick = (event: MouseEvent) => {
            if (!menuRef.current) return
            if (menuRef.current.contains(event.target as Node)) return
            setIsMenuOpen(false)
        }
        const handleKey = (event: KeyboardEvent) => {
            if (event.key === "Escape") setIsMenuOpen(false)
        }
        document.addEventListener("mousedown", handleClick)
        document.addEventListener("keydown", handleKey)
        return () => {
            document.removeEventListener("mousedown", handleClick)
            document.removeEventListener("keydown", handleKey)
        }
    }, [isMenuOpen])

    const handleClick = () => {
        if (!user) {
            void signInWithGoogle()
            return
        }
        setIsMenuOpen((prev) => !prev)
    }

    const buttonClassName = placement === "header"
        ? "group flex items-center gap-2 rounded-full border border-transparent bg-white/70 px-3 py-1.5 text-left text-sm shadow-sm transition-all hover:border-sidebar-border hover:bg-white"
        : cn(
            "group flex w-full items-center gap-3 rounded-2xl border border-transparent bg-white/70 px-3 py-2 text-left text-sm shadow-sm transition-all",
            "hover:border-sidebar-border hover:bg-white",
            collapsed && "h-9 w-9 px-0 py-0 rounded-full",
        )

    const wrapperClassName = placement === "header"
        ? "w-auto"
        : cn("relative", collapsed ? "w-9" : "w-full")

    const menuPositionClassName = placement === "header"
        ? "right-0 top-full mt-2"
        : (collapsed ? "left-full bottom-0 ml-3" : "bottom-14 left-0")

    return (
        <div className={cn("relative", wrapperClassName, className)} ref={menuRef}>
            <button
                type="button"
                onClick={handleClick}
                className={buttonClassName}
                aria-haspopup={user ? "menu" : undefined}
                aria-expanded={user ? isMenuOpen : undefined}
                aria-controls={user ? menuId : undefined}
            >
                <div className={cn(
                    "flex h-9 w-9 items-center justify-center overflow-hidden rounded-full bg-gradient-to-br from-slate-200 to-slate-100 text-xs font-semibold text-slate-500",
                    collapsed && placement !== "header" && "h-8 w-8"
                )}>
                    {avatarUrl ? (
                        <img src={avatarUrl} alt={displayName} className="h-full w-full object-cover" />
                    ) : (
                        displayName.slice(0, 1).toUpperCase()
                    )}
                </div>
                {(!collapsed || placement === "header") && (
                    <div className="min-w-0 flex-1">
                        <div className="truncate font-semibold text-slate-900">{displayName}</div>
                        <div className="truncate text-xs text-slate-500">{displayEmail}</div>
                    </div>
                )}
            </button>

            {isMenuOpen && (
                <div
                    id={menuId}
                    role="menu"
                    aria-label="Account menu"
                    className={cn(
                        "absolute z-50 w-72 rounded-2xl border border-sidebar-border bg-white shadow-2xl",
                        menuPositionClassName
                    )}
                >
                    <div className="flex items-center gap-3 rounded-t-2xl bg-slate-50 px-4 py-3">
                        <div className="h-10 w-10 overflow-hidden rounded-full bg-gradient-to-br from-slate-200 to-slate-100">
                            {avatarUrl ? (
                                <img src={avatarUrl} alt={displayName} className="h-full w-full object-cover" />
                            ) : null}
                        </div>
                        <div className="min-w-0">
                            <div className="truncate text-sm font-semibold text-slate-900">{displayName}</div>
                            <div className="truncate text-xs text-slate-500">{displayEmail}</div>
                        </div>
                    </div>

                    <div className="px-4 py-3">
                        <button
                            type="button"
                            role="menuitem"
                            className="flex w-full items-center justify-between rounded-full px-2 py-2 text-sm font-semibold text-indigo-500 hover:bg-indigo-50"
                        >
                            Upgrade Plan
                            <ChevronRight className="h-4 w-4" />
                        </button>
                        <div className="mt-2 text-sm text-slate-500">Credits: 100</div>
                    </div>

                    <div className="h-px bg-slate-100" />

                    <div className="flex flex-col gap-1 px-2 py-3 text-sm text-slate-700">
                        <button type="button" role="menuitem" className="flex w-full items-center gap-3 rounded-lg px-3 py-2 hover:bg-slate-50">
                            <Sparkles className="h-4 w-4" />
                            Business Edition
                        </button>
                        <button type="button" role="menuitem" className="flex w-full items-center gap-3 rounded-lg px-3 py-2 hover:bg-slate-50">
                            <Settings className="h-4 w-4" />
                            Settings
                        </button>
                        <button type="button" role="menuitem" className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 hover:bg-slate-50">
                            <span className="flex items-center gap-3">
                                <CircleHelp className="h-4 w-4" />
                                Help
                            </span>
                            <ChevronRight className="h-4 w-4 text-slate-400" />
                        </button>
                    </div>

                    <div className="h-px bg-slate-100" />

                    <div className="px-2 py-3">
                        <button
                            type="button"
                            role="menuitem"
                            onClick={() => {
                                setIsMenuOpen(false)
                                void signOutUser()
                            }}
                            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-slate-700 hover:bg-slate-50"
                        >
                            <LogOut className="h-4 w-4" />
                            Sign out
                        </button>
                    </div>
                </div>
            )}
        </div>
    )
}
