/**
 * Unified Polling Manager
 * 
 * Consolidates all polling operations into a single pipeline with contextual features.
 * Eliminates multiple competing intervals and provides efficient resource management.
 */

export class UnifiedPollingManager {
  constructor() {
    this.intervalId = null;
    this.isActive = false;
    this.features = new Map(); // feature_name -> config
    this.baseInterval = 500; // Base frequency: 500ms for responsiveness
    this.tickCounter = 0;
    
    // Input focus tracking to prevent polling interference
    this.isUserTyping = false;
    this.typingTimeout = null;
    this._inputTrackingSetup = false; // Lazy initialization flag
    
    // Palette interaction tracking for 3D point polling
    this.isInPalette = true; // Start assuming we're in palette
    this.paletteTimeout = null;
    this._paletteTrackingSetup = false; // Lazy initialization flag
    
    // Feature configurations
    this.featureConfigs = new Map([
      ['selection', {
        enabled: false,
        frequency: 1, // Every tick (500ms)
        handler: null,
        priority: 'high'
      }],
      ['tooltipCleanup', {
        enabled: true,
        frequency: 1, // Every tick (500ms)
        handler: null,
        priority: 'low'
      }],
      ['pointCoordinateCheck', {
        enabled: false,
        frequency: 1, // Every tick (500 ms): a moved point should update its dots promptly
        handler: null,
        priority: 'medium'
      }]
    ]);
    
    // Registered 3D Point nodes for coordinate polling
    this.registered3DPointNodes = new Map(); // nodeId -> { node, lastCoordinates, checkHandler }
  }

  /**
   * Ensure tracking systems are set up (called lazily when needed)
   */
  _ensureTrackingSetup() {
    if (!this._inputTrackingSetup) {
      this.setupInputFocusTracking();
      this._inputTrackingSetup = true;
    }
    if (!this._paletteTrackingSetup) {
      this.setupPaletteTracking();
      this._paletteTrackingSetup = true;
    }
  }

  /**
   * Start the unified polling system
   */
  start() {
    if (this.intervalId) return; // Already running
    
    // Set up tracking systems when polling actually starts
    this._ensureTrackingSetup();
    
    this.isActive = true;
    this.tickCounter = 0;
    
    this.intervalId = setInterval(() => {
      this._executeTick();
    }, this.baseInterval);
  }

  /**
   * Stop the polling system and cleanup all features
   */
  stop() {
    if (!this.intervalId) return;
    
    clearInterval(this.intervalId);
    this.intervalId = null;
    this.isActive = false;
    this.tickCounter = 0;
    
    // Disable all features
    for (const featureName of this.featureConfigs.keys()) {
      this.disableFeature(featureName);
    }
  }

  /**
   * Enable a polling feature with optional custom handler
   */
  enableFeature(featureName, handler = null) {
    if (!this.featureConfigs.has(featureName)) {
      console.warn(`[UnifiedPolling] Unknown feature: ${featureName}`);
      return false;
    }

    const config = this.featureConfigs.get(featureName);
    config.enabled = true;
    
    if (handler) {
      config.handler = handler;
    }

    // Start polling if not already running
    if (!this.isActive) {
      this.start();
    }
    
    return true;
  }

  /**
   * Disable a polling feature
   */
  disableFeature(featureName) {
    if (!this.featureConfigs.has(featureName)) {
      console.warn(`[UnifiedPolling] Unknown feature: ${featureName}`);
      return false;
    }

    this.featureConfigs.get(featureName).enabled = false;
    
    // Check if we should stop polling entirely
    this._checkAutoStop();
    return true;
  }

  /**
   * Temporarily suspend a feature (without removing handler)
   */
  suspendFeature(featureName) {
    if (this.featureConfigs.has(featureName)) {
      this.featureConfigs.get(featureName).enabled = false;
    }
  }

  /**
   * Resume a suspended feature
   */
  resumeFeature(featureName) {
    if (this.featureConfigs.has(featureName)) {
      this.featureConfigs.get(featureName).enabled = true;
      // While features were suspended, disabling another one can have stopped
      // the timer because nothing looked enabled. Start it again.
      if (!this.isActive) {
        this.start();
      }
    }
  }

  /**
   * Set custom handler for a feature
   */
  setFeatureHandler(featureName, handler) {
    if (this.featureConfigs.has(featureName)) {
      this.featureConfigs.get(featureName).handler = handler;
      return true;
    }
    return false;
  }

  /**
   * Check if polling should auto-stop when no features are enabled
   */
  _checkAutoStop() {
    const hasEnabledFeatures = Array.from(this.featureConfigs.values()).some(config => config.enabled);
    if (!hasEnabledFeatures && this.isActive) {
      this.stop();
    }
  }

  /**
   * Execute one polling tick
   */
  async _executeTick() {
    // Skip if document is hidden (palette closed)
    if (document.hidden) return;
    
    this.tickCounter++;
    
    // Execute enabled features based on their frequency
    for (const [featureName, config] of this.featureConfigs.entries()) {
      if (!config.enabled || !config.handler) continue;
      
      // Completely skip coordinate polling if user is typing or in palette UI
      if (featureName === 'pointCoordinateCheck' && (this.isUserTyping || this.isInPalette)) {
        continue;
      }
      
      // Reduce frequency of other features when actively using Noodle UI
      let effectiveFrequency = config.frequency;
      if (this.isInPalette && featureName !== 'pointCoordinateCheck') {
        // Triple the frequency interval when in palette UI (make it much slower)
        effectiveFrequency = config.frequency * 3;
        
        // Skip low-priority features entirely when in palette
        if (config.priority === 'low' && this.isUserTyping) {
          continue;
        }
      }
      
      // Check if it's time to run this feature
      if (this.tickCounter % effectiveFrequency === 0) {
        try {
          await config.handler();
        } catch (error) {
          console.error(`[UnifiedPolling] Error in ${featureName}:`, error);
        }
      }
    }
  }

  /**
   * Get status of all features
   */
  getStatus() {
    return {
      active: this.isActive,
      tickCounter: this.tickCounter,
      baseInterval: this.baseInterval,
      features: Object.fromEntries(
        Array.from(this.featureConfigs.entries()).map(([name, config]) => [
          name,
          {
            enabled: config.enabled,
            frequency: config.frequency,
            hasHandler: !!config.handler,
            effectiveInterval: config.frequency * this.baseInterval
          }
        ])
      )
    };
  }

  /**
   * Contextual feature management for common scenarios
   */
  enterSelectionMode() {
    this.inSelectionMode = true;
    this.enableFeature('selection');
  }

  exitSelectionMode() {
    this.inSelectionMode = false;
    this.disableFeature('selection');
  }

  enterHiddenMode() {
    // Suspend all features when palette is hidden
    for (const featureName of this.featureConfigs.keys()) {
      this.suspendFeature(featureName);
    }
  }

  exitHiddenMode() {
    // Resume default features when palette is visible
    this.resumeFeature('tooltipCleanup');
    // A selection that was pending when the palette was hidden must keep polling,
    // or its Select button stays on "Selecting..." with no timeout.
    if (this.inSelectionMode) {
      this.resumeFeature('selection');
    }
    
    // Resume point coordinate checking if nodes are registered
    if (this.registered3DPointNodes.size > 0) {
      this.resumeFeature('pointCoordinateCheck');
    }
  }

  /**
   * 3D Point Node Coordinate Polling Management
   */

  /**
   * Register a 3D Point node for coordinate polling
   * @param {string} nodeId - The node ID
   * @param {object} node - The node object
   * @param {function} checkHandler - Function to call when coordinates need checking
   */
  register3DPointNode(nodeId, node, checkHandler) {
    // Set up tracking systems when 3D point polling is needed
    this._ensureTrackingSetup();

    // Store initial coordinates to compare against
    const currentCoords = this._extractCurrentCoordinates(node);
    
    this.registered3DPointNodes.set(nodeId, {
      node: node,
      lastCoordinates: currentCoords,
      checkHandler: checkHandler
    });

    // Enable coordinate checking if this is the first registered node
    if (!this.featureConfigs.get('pointCoordinateCheck').enabled) {
      this._setupPointCoordinatePolling();
      this.enableFeature('pointCoordinateCheck');
      
      // Make sure polling system is running
      if (!this.isActive) {
        this.start();
      }
    }
    
  }

  /**
   * Unregister a 3D Point node from coordinate polling
   * @param {string} nodeId - The node ID to unregister
   */
  unregister3DPointNode(nodeId) {
    this.registered3DPointNodes.delete(nodeId);

    // Disable coordinate checking if no nodes are registered
    if (this.registered3DPointNodes.size === 0) {
      this.disableFeature('pointCoordinateCheck');
    }
  }

  /**
   * Setup the coordinate polling handler
   */
  _setupPointCoordinatePolling() {
    const coordinateCheckHandler = async () => {
      // Check each registered 3D Point node for coordinate changes
      for (const [nodeId, registration] of this.registered3DPointNodes) {
        try {
          await this._checkNodeCoordinates(nodeId, registration);
        } catch (error) {
          console.error(`[UnifiedPolling] Error checking coordinates for node ${nodeId}:`, error);
        }
      }
      
    };

    this.setFeatureHandler('pointCoordinateCheck', coordinateCheckHandler);
  }

  /**
   * Check if coordinates have changed for a specific 3D Point node
   */
  async _checkNodeCoordinates(nodeId, registration) {
    const { node, lastCoordinates, checkHandler } = registration;

    try {
      // Call backend to check for fresh coordinates
      const { default: fusionBridge } = await import('../bridge/FusionBridge');
      
      const response = await fusionBridge.sendMessage('checkCoordinates', {
        nodeId: nodeId,
        inputs: node.data.currentInputs || {}
      });

      if (response.success && response.coordinates_changed && response.coordinates) {
        const newCoords = response.coordinates;
        
        // Backend already determined coordinates changed - trust its judgment!
        
        // Update stored coordinates
        registration.lastCoordinates = newCoords;
        
        // Call the check handler to update the node
        if (checkHandler) {
          await checkHandler(newCoords);
        }
      }
      
    } catch (error) {
      console.error(`[UnifiedPolling] Error checking backend coordinates for node ${nodeId}:`, error);
      // Fallback to frontend coordinate comparison
      const currentCoords = this._extractCurrentCoordinates(node);
      
      if (this._coordinatesChanged(lastCoordinates, currentCoords)) {
        registration.lastCoordinates = currentCoords;
        
        if (checkHandler) {
          await checkHandler(currentCoords);
        }
      }
    }
  }

  /**
   * Extract coordinates from a 3D Point node
   */
  _extractCurrentCoordinates(node) {
    // Try multiple sources for coordinates (same as flow computation)
    if (node.data.computedOutputs?.position) {
      return { ...node.data.computedOutputs.position };
    } else if (node.data.currentInputs?.point && node.data.currentInputs.point.x !== undefined) {
      return { 
        x: node.data.currentInputs.point.x, 
        y: node.data.currentInputs.point.y, 
        z: node.data.currentInputs.point.z 
      };
    } else {
      return { x: 0, y: 0, z: 0 };
    }
  }

  /**
   * Check if coordinates have changed significantly
   */
  _coordinatesChanged(oldCoords, newCoords) {
    if (!oldCoords || !newCoords) {
      return true;
    }
    
    const tolerance = 0.001; // 1mm tolerance for coordinate changes
    
    const xChanged = Math.abs(oldCoords.x - newCoords.x) > tolerance;
    const yChanged = Math.abs(oldCoords.y - newCoords.y) > tolerance;
    const zChanged = Math.abs(oldCoords.z - newCoords.z) > tolerance;
    
    const hasChanges = xChanged || yChanged || zChanged;

    return hasChanges;
  }

  /**
   * Setup input focus tracking to pause polling when user is typing
   */
  setupInputFocusTracking() {
    // Add global event listeners for input focus/blur
    document.addEventListener('focusin', (event) => {
      const target = event.target;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) {
        this.isUserTyping = true;
        
        // Clear any existing timeout
        if (this.typingTimeout) {
          clearTimeout(this.typingTimeout);
        }
      }
    });

    document.addEventListener('focusout', (event) => {
      const target = event.target;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) {
        // Use a short delay before resuming polling to handle tab navigation
        this.typingTimeout = setTimeout(() => {
          this.isUserTyping = false;
        }, 500); // 500ms delay
      }
    });

    // Also listen for keydown events to extend the typing period
    document.addEventListener('keydown', (event) => {
      const target = event.target;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) {
        this.isUserTyping = true;
        
        // Reset the timeout
        if (this.typingTimeout) {
          clearTimeout(this.typingTimeout);
        }
        this.typingTimeout = setTimeout(() => {
          this.isUserTyping = false;
        }, 1000); // 1 second of inactivity
      }
    });
  }

  /**
   * Setup palette interaction tracking for 3D point polling
   * Focus on detecting when user is actively using OUR Noodle palette vs potentially in viewport
   */
  setupPaletteTracking() {
    // Track interactions specifically within our Noodle root div
    let lastNoodleInteraction = Date.now();
    
    const noodleInteractionEvents = ['mousedown', 'click', 'keydown', 'scroll', 'touchstart', 'input', 'focus'];
    
    noodleInteractionEvents.forEach(eventType => {
      document.addEventListener(eventType, (event) => {
        // Check if the interaction is within our Noodle root div
        const target = event.target;
        const rootDiv = document.getElementById('root');
        const isWithinNoodle = rootDiv && rootDiv.contains(target);
        
        if (isWithinNoodle) {
          lastNoodleInteraction = Date.now();
          this.isInPalette = true;
          
          // Clear any existing timeout
          if (this.paletteTimeout) {
            clearTimeout(this.paletteTimeout);
          }
          
          // Enable polling after period of UI inactivity
          this.paletteTimeout = setTimeout(() => {
            this.isInPalette = false;
          }, 2000); // 2 seconds of UI inactivity
        }
      }, { passive: true, capture: true });
    });

    // Track document visibility changes as fallback
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) {
        this.isInPalette = true;
        if (this.paletteTimeout) {
          clearTimeout(this.paletteTimeout);
          this.paletteTimeout = null;
        }
      } else {
        // Start with assumption that user is back for UI interaction
        this.isInPalette = true;
        
        // But enable polling after a brief period if no interactions
        this.paletteTimeout = setTimeout(() => {
          this.isInPalette = false;
        }, 1500);
      }
    });

  }
}

// Export singleton instance
export const unifiedPollingManager = new UnifiedPollingManager();