import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [CommonModule, RouterModule],
  template: `
    <div class="shell-container">
      <nav class="navbar">
        <div class="navbar-brand">
          <h1>MarketAI</h1>
        </div>
        <div class="navbar-menu">
          <a routerLink="/market-data" routerLinkActive="active" class="nav-link">Market Data</a>
          <a routerLink="/animated-chart" routerLinkActive="active" class="nav-link">Live Chart</a>
          <a routerLink="/ingest" routerLinkActive="active" class="nav-link">Data Ingestion</a>
          <a routerLink="/data-ranges" routerLinkActive="active" class="nav-link">Data Ranges</a>
        </div>
      </nav>
      <div class="content">
        <router-outlet></router-outlet>
      </div>
    </div>
  `,
  styles: [`
    .shell-container {
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }

    .navbar {
      background-color: #2c3e50;
      color: white;
      padding: 0 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }

    .navbar-brand h1 {
      margin: 0;
      padding: 15px 0;
      font-size: 24px;
      font-weight: bold;
    }

    .navbar-menu {
      display: flex;
      gap: 5px;
    }

    .nav-link {
      padding: 15px 20px;
      color: white;
      text-decoration: none;
      transition: background-color 0.2s;
      border-bottom: 3px solid transparent;
    }

    .nav-link:hover {
      background-color: #34495e;
    }

    .nav-link.active {
      background-color: #34495e;
      border-bottom-color: #3498db;
    }

    .content {
      flex: 1;
    }
  `]
})
export class Shell {}
