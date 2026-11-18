/**
 * Fusion 360 Communication Bridge
 * 
 * Implements the official Fusion 360 communication pattern:
 * Frontend: adsk.fusionSendData(action, jsonData)
 * Backend: HTMLEventHandler with returnData
 */

class FusionBridge {
  constructor(config = {}) {
    this.debug = config.debug || false;
    this.timeout = config.timeout || 10000; // 10 seconds
    this.retryAttempts = config.retryAttempts || 3;
    this.initialized = false;
    
    this.log = this.debug ? console.log.bind(console) : () => {};
    this.error = console.error.bind(console);
  }

  /**
   * Initialize the bridge and validate Fusion API availability
   */
  async initialize() {
    this.log('[Bridge] 🚀 Initializing Fusion communication bridge...');
    
    if (!this._validateFusionAPI()) {
      throw new Error('Fusion 360 API not available');
    }
    
    this.initialized = true;
    this.log('[Bridge] ✅ Bridge initialized successfully');
    
    // Add cleanup listeners for when palette is closed/hidden
    this._setupCleanupListeners();
    
    return true;
  }

  /**
   * Shutdown the bridge and cleanup all resources
   */
  shutdown() {
    this.log('[Bridge] 🛑 Shutting down communication bridge...');
    
    this._removeCleanupListeners();
    this.initialized = false;
    
    // Mark bridge as permanently shut down
    this._isShutdown = true;
    
    this.log('[Bridge] ✅ Bridge shutdown complete - system now inert');
  }

  /**
   * Send a message using official Fusion 360 communication pattern
   * @param {string} action - The action to perform
   * @param {object} data - Optional data payload
   * @returns {Promise<object>} Response from backend
   */
  async sendMessage(action, data = {}) {
    if (!this.initialized) {
      throw new Error('Bridge not initialized. Call initialize() first.');
    }
    
    if (this._isShutdown) {
      throw new Error('Bridge has been shut down. System is inert.');
    }

    this.log(`[Bridge] 📤 Sending: ${action}`, data);
    
    try {
      const response = await this._sendWithTimeout(action, data);
      this.log(`[Bridge] 📥 Received:`, response);
      return response;
    } catch (error) {
      this.error(`[Bridge] ❌ Communication failed for ${action}:`, error);
      throw error;
    }
  }

  /**
   * Private: Validate that Fusion API is available
   */
  _validateFusionAPI() {
    if (typeof window === 'undefined') return false;
    if (!window.adsk) return false;
    if (typeof window.adsk.fusionSendData !== 'function') return false;
    return true;
  }

  /**
   * Private: Send using official Fusion pattern with timeout and ENFORCED serialization
   */
  async _sendWithTimeout(action, data) {
    return new Promise(async (resolve, reject) => {
      const timeoutId = setTimeout(() => {
        reject(new Error(`Communication timeout after ${this.timeout}ms for action: ${action}`));
      }, this.timeout);

      try {
        // ENFORCE JSON serialization according to Fusion 360 specification
        let jsonData;
        if (data && Object.keys(data).length > 0) {
          try {
            jsonData = JSON.stringify(data);
            // Verify serialization worked by attempting to parse
            JSON.parse(jsonData);
            this.log(`[Bridge] 🔒 Serialized data: ${jsonData.length} characters`);
          } catch (serializationError) {
            clearTimeout(timeoutId);
            reject(new Error(`JSON serialization failed: ${serializationError.message}`));
            return;
          }
        } else {
          jsonData = '{}'; // Empty object as JSON string
        }
        
        // Official Fusion 360 communication pattern - MUST be exactly this format
        this.log(`[Bridge] 🔗 Calling fusionSendData('${action}', '${jsonData}')`);
        const result = window.adsk.fusionSendData(action, jsonData);
        
        this.log(`[Bridge] 🔍 fusionSendData returned:`, typeof result, result);
        
        // Check if result is a Promise (newer Fusion versions)
        if (result && typeof result.then === 'function') {
          this.log(`[Bridge] ⏳ Detected Promise, awaiting response...`);
          
          // Use Promise.resolve to handle both pending and already-resolved promises
          Promise.resolve(result)
            .then(resolvedResult => {
              clearTimeout(timeoutId);
              this.log(`[Bridge] 📨 Promise resolved:`, typeof resolvedResult, resolvedResult);
              resolve(this._parseResponse(resolvedResult));
            })
            .catch(promiseError => {
              clearTimeout(timeoutId);
              this.log(`[Bridge] ❌ Promise rejected:`, promiseError);
              reject(new Error(`Promise rejection: ${promiseError.message}`));
            });
        } else if (result === undefined || result === null) {
          // Fallback for legacy synchronous behavior
          setTimeout(() => {
            const delayedResult = this._checkForDelayedResponse();
            clearTimeout(timeoutId);
            if (delayedResult !== undefined) {
              resolve(this._parseResponse(delayedResult));
            } else {
              resolve({
                success: false,
                error: `No response received for ${action}`,
                timeout: true
              });
            }
          }, 50); // Small delay
        } else {
          // Direct synchronous response
          clearTimeout(timeoutId);
          resolve(this._parseResponse(result));
        }
        
      } catch (error) {
        clearTimeout(timeoutId);
        reject(error);
      }
    });
  }

  /**
   * Private: Check for response in various locations
   */
  _checkForDelayedResponse() {
    // Try different locations where Fusion might store the response
    const locations = [
      () => window.returnValue,
      () => window.fusionReturnValue,
      () => window.lastFusionResponse,
      () => typeof external !== 'undefined' ? external.returnValue : undefined
    ];
    
    for (let getter of locations) {
      try {
        const value = getter();
        if (value !== undefined && value !== null) {
          this.log(`[Bridge] 📨 Found delayed response:`, value);
          return value;
        }
      } catch (e) {
        // Ignore access errors
      }
    }
    
    return undefined;
  }

  /**
   * Private: Parse and validate response according to Fusion patterns with ENFORCED deserialization
   */
  _parseResponse(rawResponse) {
    if (rawResponse === undefined || rawResponse === null) {
      return {
        success: false,
        error: 'No response from backend'
      };
    }
    
    // Handle Promise objects that shouldn't reach here
    if (rawResponse && typeof rawResponse.then === 'function') {
      this.error('[Bridge] ❌ Received unresolved Promise object:', rawResponse);
      return {
        success: false,
        error: 'Received unresolved Promise object - async handling error'
      };
    }
    
    // ENFORCE JSON deserialization according to Fusion 360 specification
    if (typeof rawResponse === 'string') {
      try {
        const parsed = JSON.parse(rawResponse);
        this.log('[Bridge] 🔓 Successfully deserialized JSON response');
        
        // ENFORCE response structure - must have success field
        if (typeof parsed === 'object' && !('success' in parsed)) {
          this.error('[Bridge] ❌ Response missing required success field:', parsed);
          return {
            success: false,
            error: 'Backend response missing required success field'
          };
        }
        
        return parsed;
      } catch (e) {
        this.error('[Bridge] ❌ JSON deserialization failed:', rawResponse);
        return {
          success: false,
          error: `Invalid JSON response: ${rawResponse.substring(0, 100)}...`
        };
      }
    }
    
    if (typeof rawResponse === 'object') {
      // ENFORCE success field requirement
      if (!('success' in rawResponse)) {
        this.error('[Bridge] ❌ Object response missing required success field:', rawResponse);
        return {
          success: false,
          error: 'Backend response missing required success field'
        };
      }
      return rawResponse;
    }
    
    return {
      success: false,
      error: `Unexpected response type: ${typeof rawResponse}`
    };
  }

  /**
   * Setup cleanup listeners for palette visibility/closure
   */
  _setupCleanupListeners() {
    const handleWindowClose = () => {
      this.log('[Bridge] 🪟 Window closing - shutting down');
      this.shutdown();
    };

    // Only on pagehide, the last event before the page goes. Work that must reach
    // the add-in on the way out (the working graph's last edit) is sent on
    // beforeunload, which comes first, while the bridge still works.
    window.addEventListener('pagehide', handleWindowClose);
    this._cleanupListeners = [
      { element: window, event: 'pagehide', handler: handleWindowClose }
    ];
  }

  /**
   * Remove cleanup listeners
   */
  _removeCleanupListeners() {
    if (this._cleanupListeners) {
      for (const { element, event, handler } of this._cleanupListeners) {
        element.removeEventListener(event, handler);
      }
      this._cleanupListeners = null;
    }
  }
}

// Export singleton instance
export default new FusionBridge({ debug: false });