import { Component } from '@angular/core';
import { Shell } from './shell';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [Shell],
  template: '<app-shell></app-shell>'
})
export class App {}
