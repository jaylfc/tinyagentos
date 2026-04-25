import { useState } from "react";
import type { Project } from "@/lib/projects";
import { ProjectTaskList } from "./ProjectTaskList";
import { ProjectMembers } from "./ProjectMembers";
import { ProjectActivity } from "./ProjectActivity";
import { FilesApp } from "@/apps/FilesApp";
import { MessagesApp } from "@/apps/MessagesApp";

type Tab = "tasks" | "files" | "messages" | "members" | "activity";

export function ProjectWorkspace({ project, onChanged }: { project: Project; onChanged: () => void }) {
  const [tab, setTab] = useState<Tab>("tasks");
  return (
    <div className="flex flex-col h-full">
      <header className="px-4 py-3 border-b border-zinc-800">
        <h1 className="text-lg font-semibold">{project.name}</h1>
        <p className="text-xs text-zinc-500">{project.description}</p>
      </header>
      <nav className="flex border-b border-zinc-800 px-2" role="tablist">
        {(["tasks", "files", "messages", "members", "activity"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm capitalize ${
              tab === t ? "border-b-2 border-blue-400" : "text-zinc-400"
            }`}
          >
            {t}
          </button>
        ))}
      </nav>
      <div className="flex-1 min-h-0 overflow-auto p-4">
        {tab === "tasks" && <ProjectTaskList projectId={project.id} />}
        {tab === "files" && (
          <FilesApp
            key={project.id}
            windowId={`project-files-${project.id}`}
            rootPath={`project:${project.slug}`}
          />
        )}
        {tab === "messages" && (
          <MessagesApp
            key={project.id}
            windowId={`project-messages-${project.id}`}
            scope={{ projectId: project.id }}
          />
        )}
        {tab === "members" && <ProjectMembers project={project} onChanged={onChanged} />}
        {tab === "activity" && <ProjectActivity projectId={project.id} />}
      </div>
    </div>
  );
}
