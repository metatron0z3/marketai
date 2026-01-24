import { ComponentFixture, TestBed } from '@angular/core/testing';

import { TestRender } from './test-render';

describe('TestRender', () => {
  let component: TestRender;
  let fixture: ComponentFixture<TestRender>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TestRender]
    })
    .compileComponents();

    fixture = TestBed.createComponent(TestRender);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
