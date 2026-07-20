import { Component, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

/**
 * Catches the specific DOMException thrown by @hello-pangea/dnd during
 * Astro View Transition cleanup. dnd injects <style> tags into <head>;
 * when navigating away, Astro swaps <head> before React unmounts dnd,
 * so removeChild fails with "The node to be removed is not a child of this node".
 *
 * This boundary silently swallows that one error and renders nothing
 * (we're navigating away anyway).
 */
export class DndErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error) {
    // Silently ignore the known dnd + View Transition cleanup error
    const isDndCleanupError =
      error instanceof DOMException &&
      error.message.includes('Node.removeChild') &&
      error.name === 'NotFoundError';

    if (!isDndCleanupError) {
      // Re-throw anything unexpected — let the next boundary handle it
      console.error('DndErrorBoundary caught unexpected error:', error);
      this.setState({ hasError: false });
      throw error;
    }
  }

  render() {
    if (this.state.hasError) {
      return null;
    }
    return this.props.children;
  }
}
