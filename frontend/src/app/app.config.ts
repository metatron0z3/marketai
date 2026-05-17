import { ApplicationConfig, provideBrowserGlobalErrorListeners, InjectionToken } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http'; // Import provideHttpClient

import { routes } from './app.routes';
import { provideClientHydration, withEventReplay } from '@angular/platform-browser';
import { API_BASE_URL as EnvironmentApiBaseUrl } from './core/environment'; // Import as a different name
import { WebsocketService } from './core/services/websocket.service'; // Import WebsocketService

export const API_BASE_URL = new InjectionToken<string>('API_BASE_URL');

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideClientHydration(withEventReplay()),
    provideHttpClient(), // Add provideHttpClient here
    { provide: API_BASE_URL, useValue: EnvironmentApiBaseUrl },
    WebsocketService // Provide WebsocketService here
  ]
};
