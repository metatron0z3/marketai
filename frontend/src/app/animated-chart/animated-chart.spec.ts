import { ComponentFixture, TestBed } from '@angular/core/testing';

import { AnimatedChart } from './animated-chart';

describe('AnimatedChart', () => {
  let component: AnimatedChart;
  let fixture: ComponentFixture<AnimatedChart>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AnimatedChart]
    })
    .compileComponents();

    fixture = TestBed.createComponent(AnimatedChart);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
