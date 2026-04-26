import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { BoardToolbar } from "../BoardToolbar";
import { EMPTY_FILTERS } from "../types";

describe("BoardToolbar", () => {
  it("hides Group by selector in Kanban mode", () => {
    render(
      <BoardToolbar
        viewMode="kanban"
        groupBy="assignee"
        filters={EMPTY_FILTERS}
        live
        onChangeView={() => {}}
        onChangeGroup={() => {}}
        onChangeFilters={() => {}}
      />,
    );
    expect(screen.queryByLabelText(/Group by/)).not.toBeInTheDocument();
  });

  it("shows Group by selector in Lanes mode", () => {
    render(
      <BoardToolbar
        viewMode="lanes"
        groupBy="assignee"
        filters={EMPTY_FILTERS}
        live
        onChangeView={() => {}}
        onChangeGroup={() => {}}
        onChangeFilters={() => {}}
      />,
    );
    expect(screen.getByLabelText(/Group by/)).toBeInTheDocument();
  });

  it("emits onChangeView when a segment is clicked", () => {
    const fn = vi.fn();
    render(
      <BoardToolbar
        viewMode="lanes"
        groupBy="assignee"
        filters={EMPTY_FILTERS}
        live
        onChangeView={fn}
        onChangeGroup={() => {}}
        onChangeFilters={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("tab", { name: /Kanban/ }));
    expect(fn).toHaveBeenCalledWith("kanban");
  });
});
