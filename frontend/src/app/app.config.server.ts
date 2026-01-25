import { mergeApplicationConfig, ApplicationConfig, InjectionToken } from '@angular/core';
import { provideServerRendering, withRoutes } from '@angular/ssr';
import { appConfig } from './app.config';
import { serverRoutes } from './app.routes.server';
import { provideHttpClient } from '@angular/common/http';
import { API_BASE_URL as EnvironmentApiBaseUrl } from './core/environment';

export const API_BASE_URL = new InjectionToken<string>('API_BASE_URL');

const serverConfig: ApplicationConfig = {
  providers: [
    provideServerRendering(withRoutes(serverRoutes)),
    provideHttpClient(),
    { provide: API_BASE_URL, useValue: EnvironmentApiBaseUrl }
  ]
};

export const config = mergeApplicationConfig(appConfig, serverConfig);
