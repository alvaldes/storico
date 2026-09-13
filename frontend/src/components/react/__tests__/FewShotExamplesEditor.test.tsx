import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { FewShotExamplesEditor } from "../FewShotExamplesEditor";

const defaultExamples = [
  {
    userStory: "As a user, I want to log in so that I can access my account",
    tasks:
      "1. summary: Set up auth\ndescription: Create user and session tables.",
  },
];

const renderEditor = (props = {}) => {
  return render(
    <FewShotExamplesEditor
      locale="en"
      examples={defaultExamples}
      onChange={vi.fn()}
      maxExamples={3}
      {...props}
    />,
  );
};

describe("FewShotExamplesEditor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders existing examples", () => {
    renderEditor();

    expect(screen.getByText("User Story")).toBeInTheDocument();
    expect(screen.getByText("Expected Tasks Output")).toBeInTheDocument();
    expect(
      screen.getByDisplayValue(
        "As a user, I want to log in so that I can access my account",
      ),
    ).toBeInTheDocument();
    // Check that tasks textarea contains the expected content
    const tasksTextarea = screen.getAllByPlaceholderText(/1\. summary:/)[0];
    expect(tasksTextarea).toHaveValue(
      "1. summary: Set up auth\ndescription: Create user and session tables.",
    );
  });

  it("shows example count", () => {
    renderEditor({ examples: defaultExamples });

    expect(screen.getByText("1 / 3")).toBeInTheDocument();
  });

  it("adds new example when Add Example clicked", () => {
    const onChange = vi.fn();
    renderEditor({ examples: [], onChange });

    fireEvent.click(screen.getByText("Add Example"));

    expect(onChange).toHaveBeenCalledWith([{ userStory: "", tasks: "" }]);
  });

  it("removes example when remove button clicked", () => {
    const onChange = vi.fn();
    const examples = [
      { userStory: "Example 1", tasks: "Tasks 1" },
      { userStory: "Example 2", tasks: "Tasks 2" },
    ];
    renderEditor({ examples, onChange });

    // Click remove on first example
    const removeButtons = screen.getAllByLabelText("Remove example");
    fireEvent.click(removeButtons[0]);

    expect(onChange).toHaveBeenCalledWith([
      { userStory: "Example 2", tasks: "Tasks 2" },
    ]);
  });

  it("moves example up when up button clicked", () => {
    const onChange = vi.fn();
    const examples = [
      { userStory: "Example 1", tasks: "Tasks 1" },
      { userStory: "Example 2", tasks: "Tasks 2" },
    ];
    renderEditor({ examples, onChange });

    // Click move down on first example (moves it to position 1)
    const moveDownButtons = screen.getAllByLabelText("Move down");
    fireEvent.click(moveDownButtons[0]);

    expect(onChange).toHaveBeenCalledWith([
      { userStory: "Example 2", tasks: "Tasks 2" },
      { userStory: "Example 1", tasks: "Tasks 1" },
    ]);
  });

  it("moves example down when down button clicked", () => {
    const onChange = vi.fn();
    const examples = [
      { userStory: "Example 1", tasks: "Tasks 1" },
      { userStory: "Example 2", tasks: "Tasks 2" },
    ];
    renderEditor({ examples, onChange });

    // Click move up on second example (moves it to position 0)
    const moveUpButtons = screen.getAllByLabelText("Move up");
    fireEvent.click(moveUpButtons[1]);

    expect(onChange).toHaveBeenCalledWith([
      { userStory: "Example 2", tasks: "Tasks 2" },
      { userStory: "Example 1", tasks: "Tasks 1" },
    ]);
  });

  it("disables add button when max examples reached", () => {
    const examples = [
      {
        userStory: "Example 1 with enough characters",
        tasks: "1. summary: Task 1\ndescription: Tasks 1 description",
      },
      {
        userStory: "Example 2 with enough characters",
        tasks: "1. summary: Task 2\ndescription: Tasks 2 description",
      },
      {
        userStory: "Example 3 with enough characters",
        tasks: "1. summary: Task 3\ndescription: Tasks 3 description",
      },
    ];
    renderEditor({ examples });

    // When max examples reached, the Add Example button is replaced with a message
    expect(
      screen.getByText("Maximum of 3 few-shot examples reached"),
    ).toBeInTheDocument();
  });

  it("shows max examples reached message", () => {
    const examples = [
      { userStory: "Ex 1", tasks: "Tasks 1" },
      { userStory: "Ex 2", tasks: "Tasks 2" },
      { userStory: "Ex 3", tasks: "Tasks 3" },
    ];
    renderEditor({ examples });

    expect(
      screen.getByText("Maximum of 3 few-shot examples reached"),
    ).toBeInTheDocument();
  });

  it("shows validation error for user story too short", () => {
    const onChange = vi.fn();
    renderEditor({
      examples: [{ userStory: "", tasks: "Valid tasks description here" }],
      onChange,
    });

    const userStoryInput = screen.getAllByPlaceholderText(
      "As a user, I want to log in so that I can access my account",
    )[0];
    fireEvent.change(userStoryInput, { target: { value: "Short" } });
    fireEvent.blur(userStoryInput);

    expect(
      screen.getByText("User Story must be at least 10 characters"),
    ).toBeInTheDocument();
    expect(onChange).toHaveBeenCalledWith([
      { userStory: "Short", tasks: "Valid tasks description here" },
    ]);
  });

  it("shows validation error for tasks too short", () => {
    const onChange = vi.fn();
    renderEditor({
      examples: [{ userStory: "Valid user story here", tasks: "" }],
      onChange,
    });

    const tasksInput = screen.getAllByPlaceholderText(/1\. summary:/)[0];
    fireEvent.change(tasksInput, { target: { value: "Short" } });
    fireEvent.blur(tasksInput);

    expect(
      screen.getByText("Tasks must be at least 20 characters"),
    ).toBeInTheDocument();
  });

  it("shows validation summary when errors exist", () => {
    const onChange = vi.fn();
    // Start with valid data, then clear to trigger validation
    const examples = [
      {
        userStory: "Valid user story with enough length",
        tasks:
          "1. summary: Valid task\ndescription: Valid task description here.",
      },
    ];
    renderEditor({ examples, onChange });

    // Trigger validation by clearing fields
    const userStoryInput = screen.getAllByPlaceholderText(
      "As a user, I want to log in so that I can access my account",
    )[0];
    const tasksInput = screen.getAllByPlaceholderText(/1\. summary:/)[0];
    fireEvent.change(userStoryInput, { target: { value: "" } });
    fireEvent.change(tasksInput, { target: { value: "" } });
    fireEvent.blur(userStoryInput);
    fireEvent.blur(tasksInput);

    expect(
      screen.getByText("Fix validation errors before saving"),
    ).toBeInTheDocument();
  });

  it("disables up button on first example", () => {
    renderEditor();

    const upButtons = screen.getAllByLabelText("Move up");
    expect(upButtons[0]).toBeDisabled();
  });

  it("disables down button on last example", () => {
    renderEditor();

    const downButtons = screen.getAllByLabelText("Move down");
    expect(downButtons[0]).toBeDisabled();
  });

  it("updates example when user story changes", () => {
    const onChange = vi.fn();
    renderEditor({ onChange });

    const userStoryInput = screen.getAllByPlaceholderText(
      "As a user, I want to log in so that I can access my account",
    )[0];
    fireEvent.change(userStoryInput, {
      target: { value: "Updated user story content" },
    });

    expect(onChange).toHaveBeenCalledWith([
      {
        userStory: "Updated user story content",
        tasks:
          "1. summary: Set up auth\ndescription: Create user and session tables.",
      },
    ]);
  });

  it("updates example when tasks change", () => {
    const onChange = vi.fn();
    renderEditor({ onChange });

    const tasksInput = screen.getAllByPlaceholderText(/1\. summary:/)[0];
    fireEvent.change(tasksInput, {
      target: { value: "Updated tasks content" },
    });

    expect(onChange).toHaveBeenCalledWith([
      {
        userStory:
          "As a user, I want to log in so that I can access my account",
        tasks: "Updated tasks content",
      },
    ]);
  });

  it("shows format hint in tasks textarea placeholder", () => {
    renderEditor();

    const tasksInput = screen.getAllByPlaceholderText(/1\. summary:/)[0];
    expect(tasksInput).toHaveAttribute(
      "placeholder",
      expect.stringContaining("1. summary:"),
    );
  });

  it("applies locale-specific translations", () => {
    renderEditor({ locale: "es" });

    expect(screen.getByText("Historia de Usuario")).toBeInTheDocument();
    expect(screen.getByText("Salida de Tareas Esperada")).toBeInTheDocument();
    expect(screen.getByText("Agregar Ejemplo")).toBeInTheDocument();
  });

  it("regression: camelCase round-trip (userStory, not user_story)", () => {
    const onChange = vi.fn();
    renderEditor({ onChange });
    const input = screen.getAllByPlaceholderText(
      "As a user, I want to log in so that I can access my account",
    )[0];
    fireEvent.change(input, { target: { value: "Regression check" } });
    const call = onChange.mock.calls[0][0][0];
    expect(call).toHaveProperty("userStory");
    expect(call).not.toHaveProperty("user_story");
  });
});
