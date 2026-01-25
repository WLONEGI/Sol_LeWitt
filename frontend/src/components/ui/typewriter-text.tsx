"use client"

import { useState, useEffect, useRef, memo } from "react"
import { cn } from "@/lib/utils"
import { motion } from "framer-motion"

interface TypewriterTextProps {
    /** 表示するテキスト */
    text: string;
    /** 1文字あたりのミリ秒 (デフォルト: 15) */
    speed?: number;
    /** アニメーション完了時コールバック */
    onComplete?: () => void;
    /** カーソルを表示するか */
    showCursor?: boolean;
    /** クラス名 */
    className?: string;
}

/**
 * タイプライターエフェクトでテキストを表示するコンポーネント
 * 
 * ストリーミング中のLLM出力に最適化:
 * - 新しいテキストが追加されると、追加分のみをアニメーション
 * - 高速な更新にも対応
 */
export const TypewriterText = memo(function TypewriterText({
    text = "",
    speed = 15,
    onComplete,
    showCursor = true,
    className
}: TypewriterTextProps) {
    const [displayedLength, setDisplayedLength] = useState(0);
    const prevTextRef = useRef(text);
    const timerRef = useRef<NodeJS.Timeout | null>(null);

    useEffect(() => {
        // テキストが変更された場合
        // 前回より長くなった場合のみアニメーションを継続
        // 前回より短くなった場合（リセット）は最初から
        if (text.length < displayedLength) {
            setDisplayedLength(0);
        }

        // すでに全文表示済みなら何もしない
        if (displayedLength >= text.length) {
            if (onComplete && displayedLength === text.length && text.length > 0) {
                onComplete();
            }
            return;
        }

        // タイプライターアニメーション
        timerRef.current = setTimeout(() => {
            setDisplayedLength(prev => Math.min(prev + 1, text.length));
        }, speed);

        return () => {
            if (timerRef.current) {
                clearTimeout(timerRef.current);
            }
        };
    }, [text, displayedLength, speed, onComplete]);

    // テキストが大幅に更新された場合（ストリーミング）、追いつくためにスキップ
    useEffect(() => {
        const diff = text.length - displayedLength;
        // 50文字以上遅れている場合は追いつく（スキップ）
        if (diff > 50) {
            setDisplayedLength(text.length - 30); // 最後の30文字をアニメーション
        }
        prevTextRef.current = text;
    }, [text, displayedLength]);

    const displayedText = text.slice(0, displayedLength);
    const isComplete = displayedLength >= text.length;

    return (
        <span className={cn("relative", className)}>
            {displayedText}
            {showCursor && !isComplete && (
                <motion.span
                    className="inline-block w-[2px] h-[1em] bg-primary ml-0.5 align-middle"
                    animate={{ opacity: [1, 0] }}
                    transition={{
                        duration: 0.5,
                        repeat: Infinity,
                        repeatType: "reverse"
                    }}
                />
            )}
        </span>
    );
});

export default TypewriterText;
