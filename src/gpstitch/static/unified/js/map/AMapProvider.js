/**
 * Browser-side AMap JSAPI renderer for GPStitch preview map widgets.
 */

class AMapProvider {
    constructor() {
        this.maps = [];
        this.loaderPromise = null;
        this.loaderKey = null;
        this.convertCache = new Map();
    }

    isAmapStyle(style) {
        return style === 'amap-jsapi' || style === 'amap';
    }

    async validate(runtimeConfig) {
        const AMap = await this._load(runtimeConfig, 10000);
        const container = document.createElement('div');
        container.style.cssText = 'position:absolute;left:-9999px;top:-9999px;width:1px;height:1px;';
        document.body.appendChild(container);
        let map = null;
        try {
            map = new AMap.Map(container, {
                viewMode: '2D',
                zoom: 4,
                center: [116.397428, 39.90923],
            });
            return true;
        } finally {
            if (map) map.destroy();
            container.remove();
        }
    }

    async render(options) {
        const {
            layer,
            runtimeConfig,
            context,
            imageMetrics,
            frameTimeMs = 0,
            durationMs = 0,
        } = options;

        this.destroy();
        if (!layer || !context?.map_widgets?.length) return;

        const AMap = await this._load(runtimeConfig, 12000);
        const convertedRoute = this._convertRoute(context.route_points || [], runtimeConfig.key_fingerprint);

        layer.innerHTML = '';
        layer.classList.remove('hidden');
        layer.style.left = `${imageMetrics.left}px`;
        layer.style.top = `${imageMetrics.top}px`;
        layer.style.width = `${imageMetrics.width}px`;
        layer.style.height = `${imageMetrics.height}px`;

        const scaleX = imageMetrics.width / Math.max(1, context.canvas_width || imageMetrics.width);
        const scaleY = imageMetrics.height / Math.max(1, context.canvas_height || imageMetrics.height);
        const currentPoint = this._currentPoint(convertedRoute, frameTimeMs, durationMs);

        for (const widget of context.map_widgets) {
            const widgetEl = document.createElement('div');
            widgetEl.className = 'amap-widget';
            widgetEl.style.left = `${Math.round(widget.x * scaleX)}px`;
            widgetEl.style.top = `${Math.round(widget.y * scaleY)}px`;
            widgetEl.style.width = `${Math.max(1, Math.round(widget.width * scaleX))}px`;
            widgetEl.style.height = `${Math.max(1, Math.round(widget.height * scaleY))}px`;
            widgetEl.style.borderRadius = `${Math.max(0, Math.round((widget.corner_radius || 0) * scaleX))}px`;

            const mapEl = document.createElement('div');
            mapEl.className = 'amap-widget-map';
            widgetEl.appendChild(mapEl);
            layer.appendChild(widgetEl);

            const center = currentPoint || convertedRoute[0] || [116.397428, 39.90923];
            const map = new AMap.Map(mapEl, {
                viewMode: '2D',
                resizeEnable: true,
                zoom: widget.zoom || 16,
                center,
            });

            const overlays = [];
            if (convertedRoute.length > 1) {
                const polyline = new AMap.Polyline({
                    path: convertedRoute,
                    showDir: false,
                    strokeColor: '#1f8fff',
                    strokeOpacity: 0.9,
                    strokeWeight: 5,
                    lineJoin: 'round',
                    zIndex: 20,
                });
                map.add(polyline);
                overlays.push(polyline);
            }

            if (currentPoint) {
                const marker = new AMap.Marker({
                    position: currentPoint,
                    anchor: 'center',
                    content: '<span class="amap-current-marker"></span>',
                    zIndex: 40,
                });
                map.add(marker);
                overlays.push(marker);
            }

            if (widget.type === 'journey_map' && overlays.length > 0) {
                map.setFitView(overlays, false, [16, 16, 16, 16]);
            } else if (currentPoint) {
                map.setCenter(currentPoint);
                map.setZoom(widget.zoom || 16);
            }

            this.maps.push(map);
        }
    }

    destroy() {
        for (const map of this.maps) {
            try {
                map.destroy();
            } catch (e) {
                // Ignore provider cleanup failures during UI switches.
            }
        }
        this.maps = [];
    }

    async _load(runtimeConfig, timeoutMs) {
        if (!runtimeConfig?.configured || !runtimeConfig.key || !runtimeConfig.security_js_code) {
            throw new Error('AMap key and security JS code are required.');
        }

        window._AMapSecurityConfig = {
            securityJsCode: runtimeConfig.security_js_code,
        };

        if (!window.AMapLoader) {
            await this._loadScript('https://webapi.amap.com/loader.js', timeoutMs);
        }
        if (!window.AMapLoader?.load) {
            throw new Error('AMap loader is unavailable.');
        }

        const loaderKey = `${runtimeConfig.key_fingerprint || runtimeConfig.key}:2.0`;
        if (!this.loaderPromise || this.loaderKey !== loaderKey) {
            this.loaderKey = loaderKey;
            this.loaderPromise = this._withTimeout(
                window.AMapLoader.load({
                    key: runtimeConfig.key,
                    version: '2.0',
                    plugins: [],
                }),
                timeoutMs,
                'AMap JS API load timed out.'
            );
        }
        return this.loaderPromise;
    }

    _loadScript(src, timeoutMs) {
        return new Promise((resolve, reject) => {
            const existing = document.querySelector(`script[src="${src}"]`);
            if (existing) {
                if (window.AMapLoader) {
                    resolve();
                    return;
                }
                existing.addEventListener('load', () => resolve(), { once: true });
                existing.addEventListener('error', () => reject(new Error('Failed to load AMap loader.')), { once: true });
                return;
            }

            const script = document.createElement('script');
            const timer = window.setTimeout(() => {
                script.remove();
                reject(new Error('AMap loader timed out.'));
            }, timeoutMs);
            script.src = src;
            script.async = true;
            script.onload = () => {
                window.clearTimeout(timer);
                resolve();
            };
            script.onerror = () => {
                window.clearTimeout(timer);
                reject(new Error('Failed to load AMap loader.'));
            };
            document.head.appendChild(script);
        });
    }

    _withTimeout(promise, timeoutMs, message) {
        return new Promise((resolve, reject) => {
            const timer = window.setTimeout(() => reject(new Error(message)), timeoutMs);
            promise.then(
                value => {
                    window.clearTimeout(timer);
                    resolve(value);
                },
                error => {
                    window.clearTimeout(timer);
                    reject(error);
                }
            );
        });
    }

    _convertRoute(routePoints, fingerprint) {
        if (!routePoints.length) return [];
        const cacheKey = this._routeCacheKey(routePoints, fingerprint);
        if (this.convertCache.has(cacheKey)) return this.convertCache.get(cacheKey);

        const converted = routePoints.map(point => this._wgs84ToGcj02(point.lat, point.lon));
        this.convertCache.set(cacheKey, converted);
        return converted;
    }

    _wgs84ToGcj02(lat, lon) {
        lat = Number(lat);
        lon = Number(lon);
        if (this._outsideChina(lat, lon)) return [lon, lat];

        const a = 6378245.0;
        const ee = 0.00669342162296594323;
        let dLat = this._transformLat(lon - 105.0, lat - 35.0);
        let dLon = this._transformLon(lon - 105.0, lat - 35.0);
        const radLat = lat / 180.0 * Math.PI;
        let magic = Math.sin(radLat);
        magic = 1 - ee * magic * magic;
        const sqrtMagic = Math.sqrt(magic);
        dLat = (dLat * 180.0) / ((a * (1 - ee)) / (magic * sqrtMagic) * Math.PI);
        dLon = (dLon * 180.0) / (a / sqrtMagic * Math.cos(radLat) * Math.PI);
        return [lon + dLon, lat + dLat];
    }

    _outsideChina(lat, lon) {
        return lon < 72.004 || lon > 137.8347 || lat < 0.8293 || lat > 55.8271;
    }

    _transformLat(x, y) {
        let ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x));
        ret += (20.0 * Math.sin(6.0 * x * Math.PI) + 20.0 * Math.sin(2.0 * x * Math.PI)) * 2.0 / 3.0;
        ret += (20.0 * Math.sin(y * Math.PI) + 40.0 * Math.sin(y / 3.0 * Math.PI)) * 2.0 / 3.0;
        ret += (160.0 * Math.sin(y / 12.0 * Math.PI) + 320 * Math.sin(y * Math.PI / 30.0)) * 2.0 / 3.0;
        return ret;
    }

    _transformLon(x, y) {
        let ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x));
        ret += (20.0 * Math.sin(6.0 * x * Math.PI) + 20.0 * Math.sin(2.0 * x * Math.PI)) * 2.0 / 3.0;
        ret += (20.0 * Math.sin(x * Math.PI) + 40.0 * Math.sin(x / 3.0 * Math.PI)) * 2.0 / 3.0;
        ret += (150.0 * Math.sin(x / 12.0 * Math.PI) + 300.0 * Math.sin(x / 30.0 * Math.PI)) * 2.0 / 3.0;
        return ret;
    }

    _routeCacheKey(routePoints, fingerprint) {
        const first = routePoints[0];
        const last = routePoints[routePoints.length - 1];
        return [
            'gcj02-local-v1',
            fingerprint || 'unconfigured',
            routePoints.length,
            first?.lat,
            first?.lon,
            last?.lat,
            last?.lon,
        ].join('|');
    }

    _currentPoint(route, frameTimeMs, durationMs) {
        if (!route.length) return null;
        if (!durationMs || durationMs <= 0) return route[Math.floor(route.length / 2)];
        const ratio = Math.max(0, Math.min(1, frameTimeMs / durationMs));
        return route[Math.min(route.length - 1, Math.round(ratio * (route.length - 1)))];
    }
}

window.AMapProvider = AMapProvider;
