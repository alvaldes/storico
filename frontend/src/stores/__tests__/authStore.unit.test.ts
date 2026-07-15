import { describe, it, expect, beforeEach } from 'vitest';
import { useAuthStore } from '@/stores/authStore';

describe('authStore', () => {
  beforeEach(() => {
    // Reset store to default state before each test
    useAuthStore.setState({
      user: null,
      loading: true,
      isFirstLogin: false,
      workspaceName: '',
    });
  });

  describe('setOnboardingDone()', () => {
    it('sets isFirstLogin to false when it was true', () => {
      // Arrange
      useAuthStore.getState().setIsFirstLogin(true);
      expect(useAuthStore.getState().isFirstLogin).toBe(true);

      // Act
      useAuthStore.getState().setOnboardingDone();

      // Assert
      expect(useAuthStore.getState().isFirstLogin).toBe(false);
    });

    it('keeps isFirstLogin as false when already false', () => {
      // Arrange — already false from reset
      expect(useAuthStore.getState().isFirstLogin).toBe(false);

      // Act
      useAuthStore.getState().setOnboardingDone();

      // Assert
      expect(useAuthStore.getState().isFirstLogin).toBe(false);
    });

    it('does not affect other store fields', () => {
      // Arrange
      useAuthStore.setState({
        user: { id: '1', email: 'test@test.com', name: 'Test' },
        loading: false,
        isFirstLogin: true,
        workspaceName: 'My Workspace',
      });

      // Act
      useAuthStore.getState().setOnboardingDone();

      // Assert
      const state = useAuthStore.getState();
      expect(state.isFirstLogin).toBe(false);
      expect(state.user).toEqual({ id: '1', email: 'test@test.com', name: 'Test' });
      expect(state.loading).toBe(false);
      expect(state.workspaceName).toBe('My Workspace');
    });
  });
});
