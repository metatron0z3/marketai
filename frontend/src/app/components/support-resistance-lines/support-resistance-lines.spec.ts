import { ComponentFixture, TestBed } from '@angular/core/testing';

import { SupportResistanceLines } from './support-resistance-lines';

describe('SupportResistanceLines', () => {
  let component: SupportResistanceLines;
  let fixture: ComponentFixture<SupportResistanceLines>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SupportResistanceLines]
    })
    .compileComponents();

    fixture = TestBed.createComponent(SupportResistanceLines);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
