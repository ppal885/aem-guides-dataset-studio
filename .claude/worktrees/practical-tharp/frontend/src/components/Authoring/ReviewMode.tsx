import { useState, useCallback } from 'react'
import { Check, X, Pencil, Save, ChevronRight } from 'lucide-react'
import { Button } from '../ui/button'
import type { GeneratedDita } from '../../pages/AuthoringPage'

type SectionStatus = 'pending' | 'approved' | 'rejected' | 'editing'

interface DitaSection {
    id: string
    tag: string
    label: string
    content: string
    status: SectionStatus
    editContent: string
}

interface Props {
    dita: GeneratedDita
    onComplete: (approvedSections: DitaSection[]) => void
    onCancel: () => void
}

const TAG_COLORS: Record<string, string> = {
    shortdesc: 'bg-blue-50 text-blue-700',
    prereq:    'bg-gray-100 text-gray-600',
    context:   'bg-gray-100 text-gray-600',
    steps:     'bg-green-50 text-green-700',
    result:    'bg-green-50 text-green-700',
    section:   'bg-purple-50 text-purple-700',
    note:      'bg-amber-50 text-amber-700',
}

// Parse DITA XML into reviewable sections
function parseDitaSections(content: string): DitaSection[] {
    const sections: DitaSection[] = []

    const tags = ['shortdesc', 'prereq', 'context', 'steps', 'result', 'section', 'note']

    tags.forEach(tag => {
        const re = new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, 'gi')
        let m: string[]
        let idx = 0
        while ((m = re.exec(content)) !== null) {
            const rawContent = m[1].replace(/<[^>]+>/g, '').trim()
            if (!rawContent) continue

            // For steps, format as numbered list
            let displayContent = rawContent
            if (tag === 'steps') {
                const cmdRe = /<cmd[^>]*>([\s\S]*?)<\/cmd>/gi
                const cmds: string[] = []
                let cm: string[]
                while ((cm = cmdRe.exec(m[1])) !== null) {
                    cmds.push(cm[1].replace(/<[^>]+>/g, '').trim())
                }
                if (cmds.length > 0) {
                    displayContent = cmds.map((c, i) => `${i + 1}. ${c}`).join('\n')
                }
            }

            sections.push({
                id: `${tag}_${idx}`,
                tag,
                label: tag === 'steps'
                    ? `Steps (${displayContent.split('\n').length} steps)`
                    : tag.charAt(0).toUpperCase() + tag.slice(1),
                content: displayContent,
                status: 'pending',
                editContent: displayContent,
            })
            idx++
        }
    })

    return sections
}

export function ReviewMode({ dita, onComplete, onCancel }: Props) {
    const [sections, setSections] = useState<DitaSection[]>(() =>
        parseDitaSections(dita.content)
    )

    const update = useCallback((id: string, patch: Partial<DitaSection>) => {
        setSections(prev => prev.map(s => s.id === id ? { ...s, ...patch } : s))
    }, [])

    const approve  = (id: string) => update(id, { status: 'approved', editContent: sections.find(s => s.id === id)?.content || '' })
    const reject   = (id: string) => update(id, { status: 'rejected' })
    const startEdit = (id: string) => update(id, { status: 'editing' })
    const cancelEdit = (id: string) => update(id, { status: 'pending' })
    const saveEdit  = (id: string) => {
        const sec = sections.find(s => s.id === id)
        if (!sec) return
        update(id, { status: 'approved', content: sec.editContent })
    }

    const approved = sections.filter(s => s.status === 'approved')
    const rejected = sections.filter(s => s.status === 'rejected')
    const allReviewed = sections.every(s => s.status !== 'pending' && s.status !== 'editing')

    const firstPending = sections.findIndex(s => s.status === 'pending')

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
                <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-blue-600 bg-blue-50 px-2 py-0.5 rounded">
            {dita.filename}
          </span>
                    <ChevronRight className="w-3 h-3 text-gray-400" />
                    <span className="text-xs font-medium text-gray-700">Review Mode</span>
                    <span className="text-xs text-gray-400">— approve each section before saving</span>
                </div>
                <div className="flex items-center gap-3">
                    {/* Progress dots */}
                    <div className="flex gap-1.5 items-center">
                        {sections.map(s => (
                            <div
                                key={s.id}
                                title={s.label}
                                className={`w-2 h-2 rounded-full transition-colors ${
                                    s.status === 'approved' ? 'bg-green-500'
                                        : s.status === 'rejected' ? 'bg-red-400'
                                            : s.status === 'editing'  ? 'bg-amber-400'
                                                : 'bg-gray-200'
                                }`}
                            />
                        ))}
                    </div>
                    <span className="text-xs text-gray-500">
            {approved.length}/{sections.length} approved
          </span>
                    <button
                        onClick={onCancel}
                        className="text-xs text-gray-400 hover:text-gray-600 px-2 py-1 rounded hover:bg-gray-100"
                    >
                        Exit review
                    </button>
                </div>
            </div>

            {/* Sections */}
            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
                {sections.map((sec, i) => {
                    const isActive = i === firstPending
                    const tagColor = TAG_COLORS[sec.tag] || 'bg-gray-100 text-gray-600'

                    return (
                        <div
                            key={sec.id}
                            className={`rounded-lg border transition-all overflow-hidden ${
                                sec.status === 'approved' ? 'border-green-400 bg-green-50/30'
                                    : sec.status === 'rejected' ? 'border-red-300 opacity-50'
                                        : sec.status === 'editing'  ? 'border-amber-400'
                                            : isActive ? 'border-blue-400 border-[1.5px]'
                                                : 'border-gray-200'
                            }`}
                        >
                            {/* Section header */}
                            <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100">
                                <div className="flex items-center gap-2">
                  <span className={`text-xs font-mono font-medium px-1.5 py-0.5 rounded ${tagColor}`}>
                    {sec.tag}
                  </span>
                                    <span className="text-xs text-gray-500">{sec.label}</span>
                                </div>
                                <StatusBadge status={sec.status} isActive={isActive} />
                            </div>

                            {/* Section content */}
                            <div className="px-4 py-3">
                                {sec.status === 'editing' ? (
                                    <textarea
                                        value={sec.editContent}
                                        onChange={e => update(sec.id, { editContent: e.target.value })}
                                        className="w-full text-xs font-sans text-gray-700 bg-white border border-gray-200 rounded-md p-2.5 resize-y min-h-[80px] focus:outline-none focus:border-blue-400"
                                        autoFocus
                                    />
                                ) : (
                                    <p className="text-xs text-gray-700 leading-relaxed whitespace-pre-line">
                                        {sec.content}
                                    </p>
                                )}
                            </div>

                            {/* Action buttons */}
                            {(sec.status === 'pending' || sec.status === 'editing') && (
                                <div className="flex gap-2 px-4 py-2.5 bg-gray-50 border-t border-gray-100">
                                    {sec.status === 'editing' ? (
                                        <>
                                            <button
                                                onClick={() => saveEdit(sec.id)}
                                                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-green-50 text-green-700 border border-green-300 hover:bg-green-100 transition-colors"
                                            >
                                                <Save className="w-3 h-3" />
                                                Save edit
                                            </button>
                                            <button
                                                onClick={() => cancelEdit(sec.id)}
                                                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md border border-gray-200 hover:bg-gray-100 transition-colors text-gray-600"
                                            >
                                                Cancel
                                            </button>
                                        </>
                                    ) : (
                                        <>
                                            <button
                                                onClick={() => approve(sec.id)}
                                                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-green-50 text-green-700 border border-green-300 hover:bg-green-100 transition-colors font-medium"
                                            >
                                                <Check className="w-3 h-3" />
                                                Approve
                                            </button>
                                            <button
                                                onClick={() => startEdit(sec.id)}
                                                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-blue-50 text-blue-700 border border-blue-300 hover:bg-blue-100 transition-colors"
                                            >
                                                <Pencil className="w-3 h-3" />
                                                Rewrite
                                            </button>
                                            <button
                                                onClick={() => reject(sec.id)}
                                                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-red-50 text-red-700 border border-red-300 hover:bg-red-100 transition-colors"
                                            >
                                                <X className="w-3 h-3" />
                                                Reject
                                            </button>
                                        </>
                                    )}
                                </div>
                            )}

                            {/* Approved — undo option */}
                            {sec.status === 'approved' && (
                                <div className="flex items-center justify-between px-4 py-2 bg-green-50/50 border-t border-green-100">
                  <span className="text-xs text-green-600 flex items-center gap-1">
                    <Check className="w-3 h-3" />
                    Approved
                  </span>
                                    <button
                                        onClick={() => update(sec.id, { status: 'pending' })}
                                        className="text-xs text-gray-400 hover:text-gray-600"
                                    >
                                        Undo
                                    </button>
                                </div>
                            )}

                            {/* Rejected — undo option */}
                            {sec.status === 'rejected' && (
                                <div className="flex items-center justify-between px-4 py-2 bg-red-50/50 border-t border-red-100">
                  <span className="text-xs text-red-500 flex items-center gap-1">
                    <X className="w-3 h-3" />
                    Excluded from output
                  </span>
                                    <button
                                        onClick={() => update(sec.id, { status: 'pending' })}
                                        className="text-xs text-gray-400 hover:text-gray-600"
                                    >
                                        Undo
                                    </button>
                                </div>
                            )}
                        </div>
                    )
                })}

                {/* Summary + Save */}
                {allReviewed && (
                    <div className="bg-gray-50 rounded-lg border border-gray-200 p-4 mt-4">
                        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
                            Review complete
                        </p>
                        <div className="flex gap-3 mb-4">
                            <div className="flex-1 bg-white rounded-md border border-green-300 p-3">
                                <p className="text-xs text-green-700 font-medium mb-0.5">Approved</p>
                                <p className="text-2xl font-medium text-green-600">{approved.length}</p>
                                <p className="text-xs text-gray-400 mt-1">
                                    {approved.map(s => s.tag).join(', ')}
                                </p>
                            </div>
                            <div className="flex-1 bg-white rounded-md border border-red-300 p-3">
                                <p className="text-xs text-red-600 font-medium mb-0.5">Rejected</p>
                                <p className="text-2xl font-medium text-red-500">{rejected.length}</p>
                                <p className="text-xs text-gray-400 mt-1">
                                    {rejected.length > 0 ? rejected.map(s => s.tag).join(', ') : 'None'}
                                </p>
                            </div>
                        </div>
                        <Button
                            onClick={() => onComplete(approved)}
                            disabled={approved.length === 0}
                            className="w-full bg-blue-600 hover:bg-blue-700 text-white text-sm"
                        >
                            Save {approved.length} approved section{approved.length !== 1 ? 's' : ''} to {dita.filename}
                        </Button>
                        {approved.length === 0 && (
                            <p className="text-xs text-red-500 text-center mt-2">
                                Approve at least one section to save
                            </p>
                        )}
                    </div>
                )}
            </div>
        </div>
    )
}

function StatusBadge({ status, isActive }: { status: SectionStatus; isActive: boolean }) {
    if (status === 'approved') return (
        <span className="text-xs px-2 py-0.5 rounded bg-green-50 text-green-700 font-medium">Approved</span>
    )
    if (status === 'rejected') return (
        <span className="text-xs px-2 py-0.5 rounded bg-red-50 text-red-600 font-medium">Rejected</span>
    )
    if (status === 'editing') return (
        <span className="text-xs px-2 py-0.5 rounded bg-amber-50 text-amber-700 font-medium">Editing</span>
    )
    if (isActive) return (
        <span className="text-xs px-2 py-0.5 rounded bg-blue-50 text-blue-700 font-medium">Review now</span>
    )
    return (
        <span className="text-xs px-2 py-0.5 rounded bg-gray-100 text-gray-400">Pending</span>
    )
}
