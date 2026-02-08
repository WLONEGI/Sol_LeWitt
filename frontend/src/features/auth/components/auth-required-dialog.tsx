"use client"

import { LogIn } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

interface AuthRequiredDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onLogin: () => Promise<void> | void
  isLoading?: boolean
  error?: string | null
}

export function AuthRequiredDialog({
  open,
  onOpenChange,
  onLogin,
  isLoading = false,
  error,
}: AuthRequiredDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg rounded-[28px] border-gray-200 bg-white/95 px-6 py-5 backdrop-blur-xl">
        <DialogHeader className="space-y-2">
          <DialogTitle className="text-xl tracking-tight">ログインして続行</DialogTitle>
          <DialogDescription className="text-[14px] leading-6 text-gray-600">
            メッセージの送信にはアカウント連携が必要です。Googleでログインすると、そのまま続きから開始できます。
          </DialogDescription>
        </DialogHeader>

        {error ? (
          <div className="mt-3 rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
            {error}
          </div>
        ) : null}

        <DialogFooter className="mt-4">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isLoading}
            className="rounded-full border-gray-200"
          >
            キャンセル
          </Button>
          <Button onClick={onLogin} disabled={isLoading} className="rounded-full">
            <LogIn className="mr-2 h-4 w-4" />
            {isLoading ? "ログイン中..." : "Googleでログイン"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
