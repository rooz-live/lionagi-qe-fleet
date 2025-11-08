#!/usr/bin/env python3
"""Coverage gap analyzer - identifies modules below coverage thresholds"""
import json
import sys
import argparse
from pathlib import Path


def analyze_coverage(coverage_file, target=0.85, core_target=0.90):
    """Analyze coverage and group modules by coverage percentage"""
    
    with open(coverage_file) as f:
        data = json.load(f)
    
    total_coverage = data['totals']['percent_covered']
    files = data['files']
    
    # Define core modules
    core_modules = {
        'src/lionagi_qe/core/base_agent.py',
        'src/lionagi_qe/core/fleet.py',
        'src/lionagi_qe/core/orchestrator.py',
        'src/lionagi_qe/core/router.py',
        'src/lionagi_qe/core/hooks.py',
        'src/lionagi_qe/core/memory.py',
        'src/lionagi_qe/core/task.py',
    }
    
    learning_modules = {
        'src/lionagi_qe/learning/qlearner.py',
        'src/lionagi_qe/learning/db_manager.py',
        'src/lionagi_qe/learning/reward_calculator.py',
        'src/lionagi_qe/learning/state_encoder.py',
    }
    
    # Group by coverage buckets
    buckets = {
        'critical': [],    # <20%
        'low': [],         # 20-60%
        'medium': [],      # 60-80%
        'good': [],        # 80-90%
        'excellent': [],   # >90%
    }
    
    for path, metrics in sorted(files.items()):
        pct = metrics['summary']['percent_covered']
        lines_total = metrics['summary']['num_statements']
        lines_missing = metrics['summary']['missing_lines']
        name = path.replace('src/lionagi_qe/', '')
        
        is_core = path in core_modules
        is_learning = path in learning_modules
        priority = '🔴' if is_core else '🟡' if is_learning else '🟢'
        
        module_info = {
            'name': name,
            'coverage': pct,
            'lines_total': lines_total,
            'lines_missing': lines_missing,
            'priority': priority,
            'type': 'Core' if is_core else 'Learning' if is_learning else 'Agent',
            'path': path
        }
        
        if pct < 20:
            buckets['critical'].append(module_info)
        elif pct < 60:
            buckets['low'].append(module_info)
        elif pct < 80:
            buckets['medium'].append(module_info)
        elif pct < 90:
            buckets['good'].append(module_info)
        else:
            buckets['excellent'].append(module_info)
    
    return {
        'total_coverage': total_coverage,
        'buckets': buckets,
        'target': target,
        'core_target': core_target
    }


def print_analysis(analysis):
    """Print coverage analysis to console"""
    
    print(f"\n{'='*80}")
    print(f"COVERAGE ANALYSIS - Overall: {analysis['total_coverage']:.1f}%")
    print(f"Target: {analysis['target']*100:.0f}% | Core Target: {analysis['core_target']*100:.0f}%")
    print(f"{'='*80}\n")
    
    for bucket_name, modules in analysis['buckets'].items():
        if not modules:
            continue
            
        print(f"\n## {bucket_name.upper()} (<{len(modules)} modules>)")
        print(f"{'-'*80}")
        
        for m in sorted(modules, key=lambda x: x['coverage']):
            print(f"{m['priority']} {m['coverage']:5.1f}% | {m['lines_missing']:4d} lines | "
                  f"{m['type']:8s} | {m['name']}")


def export_markdown(analysis, output_file):
    """Export analysis to markdown file"""
    
    with open(output_file, 'w') as f:
        f.write(f"# Coverage Baseline Report\n\n")
        f.write(f"**Overall Coverage**: {analysis['total_coverage']:.1f}%  \n")
        f.write(f"**Target**: {analysis['target']*100:.0f}%  \n")
        f.write(f"**Core Target**: {analysis['core_target']*100:.0f}%  \n\n")
        
        for bucket_name, modules in analysis['buckets'].items():
            if not modules:
                continue
                
            f.write(f"\n## {bucket_name.title()} Coverage\n\n")
            f.write("| Coverage | Missing Lines | Type | Module |\n")
            f.write("|----------|---------------|------|--------|\n")
            
            for m in sorted(modules, key=lambda x: x['coverage']):
                f.write(f"| {m['coverage']:.1f}% | {m['lines_missing']} | "
                       f"{m['type']} | `{m['name']}` |\n")


def main():
    parser = argparse.ArgumentParser(description='Analyze test coverage gaps')
    parser.add_argument('--coverage-file', default='coverage.json',
                       help='Path to coverage.json file')
    parser.add_argument('--target', type=float, default=0.85,
                       help='Target coverage percentage (default: 0.85)')
    parser.add_argument('--core-target', type=float, default=0.90,
                       help='Core modules target coverage (default: 0.90)')
    parser.add_argument('--output', default='reports/coverage_baseline.md',
                       help='Output markdown file')
    
    args = parser.parse_args()
    
    if not Path(args.coverage_file).exists():
        print(f"Error: Coverage file not found: {args.coverage_file}", file=sys.stderr)
        print("Run: pytest --cov=src/lionagi_qe --cov-report=json", file=sys.stderr)
        sys.exit(1)
    
    analysis = analyze_coverage(args.coverage_file, args.target, args.core_target)
    
    print_analysis(analysis)
    
    # Export to markdown
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    export_markdown(analysis, output_path)
    print(f"\n✓ Report exported to: {output_path}")
    
    # Exit with error code if below target
    if analysis['total_coverage'] < args.target * 100:
        sys.exit(1)


if __name__ == '__main__':
    main()
