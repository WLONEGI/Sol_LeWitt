
"use client"

import { useResearchStore } from "@/features/preview/stores/research"
import { ResearchStatusButton } from "./message/research-status-button"
import { AnimatePresence, motion } from "framer-motion"

export function ActiveResearchList() {
    const tasks = useResearchStore((state) => state.tasks)
    const taskList = Object.values(tasks)

    if (taskList.length === 0) return null

    return (
        <div className="w-full max-w-3xl flex flex-wrap gap-2 mb-2 pointer-events-auto">
            <AnimatePresence>
                {taskList.map((task) => (
                    <motion.div
                        key={task.taskId}
                        initial={{ opacity: 0, scale: 0.9, y: 5 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.9 }}
                    >
                        <ResearchStatusButton
                            taskId={task.taskId}
                            perspective={task.perspective}
                            status={task.status}
                        />
                    </motion.div>
                ))}
            </AnimatePresence>
        </div>
    )
}
