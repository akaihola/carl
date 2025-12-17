// Location context acquisition
window.Carl = window.Carl || {};

Carl.location = {
    async getContext() {
        const { state, helpers } = Carl;

        if (state.cachedLocationContext) {
            return state.cachedLocationContext;
        }

        const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

        try {
            const position = await new Promise((resolve, reject) => {
                navigator.geolocation.getCurrentPosition(resolve, reject, {
                    enableHighAccuracy: true,
                    timeout: 10000,
                    maximumAge: 300000
                });
            });

            const { latitude, longitude } = position.coords;
            const timestamp = helpers.formatTimestamp();

            let locationDetails = { country: '', state: '', city: '', address: '' };
            try {
                const response = await fetch(
                    `https://nominatim.openstreetmap.org/reverse?lat=${latitude}&lon=${longitude}&format=json&addressdetails=1`,
                    { headers: { 'User-Agent': 'Carl AI Assistant' } }
                );
                const data = await response.json();
                const addr = data.address || {};
                locationDetails = {
                    country: addr.country || '',
                    state: addr.state || addr.region || '',
                    city: addr.city || addr.town || addr.village || addr.municipality || '',
                    address: data.display_name || ''
                };
            } catch (e) {
                console.warn('[LOCATION] Reverse geocoding failed:', e);
            }

            state.cachedLocationContext = `CURRENT CONTEXT:
Timestamp: ${timestamp}
Timezone: ${timezone}
Location: ${latitude.toFixed(6)}, ${longitude.toFixed(6)}
Country: ${locationDetails.country}
State/Province: ${locationDetails.state}
City: ${locationDetails.city}
Address: ${locationDetails.address}

`;
            console.log('[LOCATION] Context acquired:', state.cachedLocationContext);
            return state.cachedLocationContext;

        } catch (e) {
            console.warn('[LOCATION] Geolocation failed:', e);
            const timestamp = helpers.formatTimestamp();

            state.cachedLocationContext = `CURRENT CONTEXT:
Timestamp: ${timestamp}
Timezone: ${timezone}
Location: Not available (permission denied or unavailable)

`;
            return state.cachedLocationContext;
        }
    }
};
