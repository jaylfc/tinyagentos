import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { TypingFooter } from "../TypingFooter";

describe("TypingFooter", () => {
  it("renders nothing when empty", () => {
    const { container } = render(<TypingFooter humans={[]} agents={[]} />);
    expect(container.firstChild).toBeNull();
  });
  it("shows one human typing", () => {
    render(<TypingFooter humans={["alice"]} agents={[]} />);
    expect(screen.getByText("alice is typing…")).toBeInTheDocument();
  });
  it("shows N others when humans > 2", () => {
    render(<TypingFooter humans={["alice", "bob", "carol"]} agents={[]} />);
    expect(screen.getByText("alice and 2 others are typing…")).toBeInTheDocument();
  });
  it("filters self out of humans", () => {
    const { container } = render(<TypingFooter humans={["user"]} agents={[]} selfId="user" />);
    expect(container.firstChild).toBeNull();
  });
  it("joins multiple agents with middle dot", () => {
    render(<TypingFooter humans={[]} agents={["tom", "don"]} />);
    expect(screen.getByText("tom is thinking… · don is thinking…")).toBeInTheDocument();
  });
});
