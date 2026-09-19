import { describe, expect, it } from 'vitest';

import { ApiRequestError } from '@/lib/api';
import { extractErrorInfo } from '@/lib/error-info';

describe('extractErrorInfo', () => {
  it('keeps everything an ApiRequestError captured', () => {
    // The reason this function exists: the store used to keep only `err.message`, so the error
    // card could not show the status, the code or the body the server actually sent.
    const err = new ApiRequestError(
      409,
      'Conflict',
      { error_code: 'INVALID_STATE_TRANSITION', current_state: 'todo', attempted_state: 'done' },
      { detail: 'cannot move there' },
    );

    expect(extractErrorInfo(err)).toEqual({
      friendlyMessage: err.message,
      rawDetail: { detail: 'cannot move there' },
      status: 409,
      errorCode: 'INVALID_STATE_TRANSITION',
    });
  });

  it('does not mistake a look-alike object for an ApiRequestError', () => {
    // Regression guard for the copy this replaced, which classified by shape with
    // `'detail' in err && 'status' in err`. Any payload with those two keys satisfied it, and
    // nothing else about the object was inspected.
    const lookAlike = { detail: 'nope', status: 500, message: 'looks like one' };

    const info = extractErrorInfo(lookAlike, 'fell back');

    expect(info).toEqual({ friendlyMessage: 'fell back', rawDetail: lookAlike });
    expect(info.status).toBeUndefined();
    expect(info.errorCode).toBeUndefined();
  });

  it('reads a plain Error', () => {
    expect(extractErrorInfo(new Error('boom'))).toEqual({
      friendlyMessage: 'boom',
      // The detail falls back to the message so the disclosure panel is never empty.
      rawDetail: 'boom',
    });
  });

  it('reads a thrown string', () => {
    expect(extractErrorInfo('just a string')).toEqual({
      friendlyMessage: 'just a string',
      rawDetail: 'just a string',
    });
  });

  it('uses the caller’s fallback when there is nothing readable', () => {
    expect(extractErrorInfo(undefined, 'Extraction failed')).toEqual({
      friendlyMessage: 'Extraction failed',
      rawDetail: undefined,
    });
    expect(extractErrorInfo({ weird: true }, 'Extraction failed').friendlyMessage).toBe(
      'Extraction failed',
    );
  });

  it('has a generic fallback of its own', () => {
    expect(extractErrorInfo(null).friendlyMessage).toBe('An unknown error occurred');
  });
});
