"""
Statistical Tester for Strategy Evaluation
-----------------------------------------
Performs statistical tests to compare trading strategies.
"""

import numpy as np
import pandas as pd
from scipy import stats
from typing import Dict, List, Any, Optional, Tuple, Union


class StatisticalTester:
    """
    Performs statistical tests to compare trading strategies.
    
    This class implements various statistical tests to determine if the 
    performance difference between strategies is statistically significant.
    """
    
    def __init__(self, 
                 alpha: float = 0.05,
                 multiple_test_correction: str = 'bonferroni'):
        """
        Initialize the statistical tester.
        
        Args:
            alpha: Significance level (default: 0.05)
            multiple_test_correction: Method for multiple test correction
                ('bonferroni', 'holm', 'benjamini-hochberg', or None)
        """
        self.alpha = alpha
        self.multiple_test_correction = multiple_test_correction
        
        # Valid correction methods
        self.valid_corrections = ['bonferroni', 'holm', 'benjamini-hochberg', None]
        
        if multiple_test_correction not in self.valid_corrections:
            raise ValueError(f"multiple_test_correction must be one of {self.valid_corrections}")
    
    def compare_means(self, 
                      returns1: np.ndarray, 
                      returns2: np.ndarray,
                      paired: bool = True,
                      equal_var: bool = False) -> Dict[str, Any]:
        """
        Compare the means of two return series.
        
        Args:
            returns1: Returns of the first strategy
            returns2: Returns of the second strategy
            paired: Whether the samples are paired (same time period)
            equal_var: Whether to assume equal variance
            
        Returns:
            Dictionary with test statistics and results
        """
        # Check if data is paired and lengths match
        if paired and len(returns1) != len(returns2):
            raise ValueError("Paired samples must have the same length")
        
        # Remove NaN values
        if paired:
            # For paired data, we need valid returns for both strategies at the same times
            valid_indices = ~np.isnan(returns1) & ~np.isnan(returns2)
            valid_returns1 = returns1[valid_indices]
            valid_returns2 = returns2[valid_indices]
        else:
            valid_returns1 = returns1[~np.isnan(returns1)]
            valid_returns2 = returns2[~np.isnan(returns2)]
        
        # Check if we have enough data
        if len(valid_returns1) < 2 or len(valid_returns2) < 2:
            return {
                'test': 't-test',
                'p_value': np.nan,
                't_statistic': np.nan,
                'significant': False,
                'better_strategy': None,
                'error': 'Insufficient valid data for hypothesis testing'
            }
        
        # Perform the appropriate t-test
        try:
            if paired:
                t_stat, p_value = stats.ttest_rel(valid_returns1, valid_returns2)
            else:
                t_stat, p_value = stats.ttest_ind(valid_returns1, valid_returns2, equal_var=equal_var)
            
            # Determine which strategy is better
            better_strategy = 1 if np.mean(valid_returns1) > np.mean(valid_returns2) else 2
            
            return {
                'test': 't-test (paired)' if paired else 't-test (independent)',
                'p_value': p_value,
                't_statistic': t_stat,
                'significant': p_value < self.alpha,
                'better_strategy': better_strategy if p_value < self.alpha else None
            }
        except Exception as e:
            return {
                'test': 't-test',
                'p_value': np.nan,
                't_statistic': np.nan,
                'significant': False,
                'better_strategy': None,
                'error': str(e)
            }
    
    def compare_sharpe_ratios(self, 
                              returns1: np.ndarray, 
                              returns2: np.ndarray,
                              rf_rate: float = 0.0,
                              periods_per_year: int = 252) -> Dict[str, Any]:
        """
        Compare the Sharpe ratios of two return series using the Jobson-Korkie test.
        
        Args:
            returns1: Returns of the first strategy
            returns2: Returns of the second strategy
            rf_rate: Risk-free rate (daily)
            periods_per_year: Number of periods per year
            
        Returns:
            Dictionary with test statistics and results
        """
        # Remove NaN values and ensure same length
        valid_indices = ~np.isnan(returns1) & ~np.isnan(returns2)
        valid_returns1 = returns1[valid_indices]
        valid_returns2 = returns2[valid_indices]
        
        if len(valid_returns1) < 30:  # Need reasonable sample size
            return {
                'test': 'Sharpe ratio test',
                'p_value': np.nan,
                'z_statistic': np.nan,
                'significant': False,
                'better_strategy': None,
                'error': 'Insufficient data for Sharpe ratio test (need at least 30 observations)'
            }
        
        try:
            # Calculate mean and variance for each return series
            mean1 = np.mean(valid_returns1)
            mean2 = np.mean(valid_returns2)
            
            var1 = np.var(valid_returns1, ddof=1)
            var2 = np.var(valid_returns2, ddof=1)
            
            # Calculate covariance
            cov12 = np.cov(valid_returns1, valid_returns2, ddof=1)[0, 1]
            
            # Calculate Sharpe ratios
            sr1 = (mean1 - rf_rate) / np.sqrt(var1)
            sr2 = (mean2 - rf_rate) / np.sqrt(var2)
            
            # Calculate test statistic (Jobson-Korkie)
            n = len(valid_returns1)
            
            # Calculate components
            s_ratio = (2 * var1 * var2 - 2 * cov12 * np.sqrt(var1) * np.sqrt(var2)) / n
            s_mean = (var1 * var2 * (1 - cov12**2 / (var1 * var2))) / n
            
            s1 = (var1 * mean2**2 + var2 * mean1**2 - 2 * mean1 * mean2 * cov12) / (2 * var1 * var2 - 2 * cov12**2)
            s2 = (mean1**2 / var1 + mean2**2 / var2 - 2 * mean1 * mean2 * cov12 / (np.sqrt(var1) * np.sqrt(var2)))
            
            # Asymptotic test statistic
            z_stat = (sr1 - sr2) / np.sqrt(s_ratio + s_mean)
            
            # p-value from normal distribution
            p_value = 2 * (1 - stats.norm.cdf(abs(z_stat)))
            
            # Determine which strategy is better
            better_strategy = 1 if sr1 > sr2 else 2
            
            return {
                'test': 'Sharpe ratio test (Jobson-Korkie)',
                'p_value': p_value,
                'z_statistic': z_stat,
                'significant': p_value < self.alpha,
                'better_strategy': better_strategy if p_value < self.alpha else None,
                'sharpe1': sr1 * np.sqrt(periods_per_year),  # Annualized
                'sharpe2': sr2 * np.sqrt(periods_per_year)   # Annualized
            }
        except Exception as e:
            return {
                'test': 'Sharpe ratio test',
                'p_value': np.nan,
                'z_statistic': np.nan,
                'significant': False,
                'better_strategy': None,
                'error': str(e)
            }
    
    def bootstrap_comparison(self,
                             returns1: np.ndarray,
                             returns2: np.ndarray,
                             metric_func: callable,
                             n_iterations: int = 1000,
                             sample_size: Optional[int] = None,
                             random_seed: Optional[int] = None) -> Dict[str, Any]:
        """
        Perform bootstrap comparison for any metric.
        
        Args:
            returns1: Returns of the first strategy
            returns2: Returns of the second strategy
            metric_func: Function to calculate the metric of interest
            n_iterations: Number of bootstrap iterations
            sample_size: Size of each bootstrap sample (default: same as input)
            random_seed: Random seed for reproducibility
            
        Returns:
            Dictionary with bootstrap results
        """
        # Remove NaN values
        valid_returns1 = returns1[~np.isnan(returns1)]
        valid_returns2 = returns2[~np.isnan(returns2)]
        
        if len(valid_returns1) < 10 or len(valid_returns2) < 10:
            return {
                'test': 'Bootstrap comparison',
                'p_value': np.nan,
                'significant': False,
                'better_strategy': None,
                'error': 'Insufficient data for bootstrap (need at least 10 observations)'
            }
        
        # Set sample size if not provided
        if sample_size is None:
            sample_size = min(len(valid_returns1), len(valid_returns2))
        
        # Set random seed
        if random_seed is not None:
            np.random.seed(random_seed)
        
        # Calculate original metric difference
        original_metric1 = metric_func(valid_returns1)
        original_metric2 = metric_func(valid_returns2)
        original_diff = original_metric1 - original_metric2
        
        # Perform bootstrap
        bootstrap_diffs = []
        
        for _ in range(n_iterations):
            # Sample with replacement
            sample1 = np.random.choice(valid_returns1, size=sample_size, replace=True)
            sample2 = np.random.choice(valid_returns2, size=sample_size, replace=True)
            
            # Calculate metric for bootstrap samples
            metric1 = metric_func(sample1)
            metric2 = metric_func(sample2)
            
            # Store difference
            bootstrap_diffs.append(metric1 - metric2)
        
        # Calculate p-value (two-sided test)
        bootstrap_diffs = np.array(bootstrap_diffs)
        p_value = np.mean(np.abs(bootstrap_diffs) >= np.abs(original_diff))
        
        # Determine which strategy is better
        better_strategy = 1 if original_diff > 0 else 2
        
        return {
            'test': 'Bootstrap comparison',
            'p_value': p_value,
            'significant': p_value < self.alpha,
            'better_strategy': better_strategy if p_value < self.alpha else None,
            'original_diff': original_diff,
            'bootstrap_mean_diff': np.mean(bootstrap_diffs),
            'bootstrap_std_diff': np.std(bootstrap_diffs),
            'ci_lower': np.percentile(bootstrap_diffs, 2.5),
            'ci_upper': np.percentile(bootstrap_diffs, 97.5)
        }
    
    def multiple_test_correction_adjust(self, p_values: List[float]) -> List[float]:
        """
        Apply multiple test correction to p-values.
        
        Args:
            p_values: List of p-values
            
        Returns:
            Adjusted p-values
        """
        if self.multiple_test_correction is None:
            return p_values
        
        p_values = np.array(p_values)
        n = len(p_values)
        
        if self.multiple_test_correction == 'bonferroni':
            # Bonferroni correction
            adjusted_p_values = np.minimum(p_values * n, 1.0)
            
        elif self.multiple_test_correction == 'holm':
            # Holm-Bonferroni method
            indices = np.argsort(p_values)
            sorted_p_values = p_values[indices]
            adjusted_sorted_p_values = np.zeros_like(sorted_p_values)
            
            for i in range(n):
                adjusted_sorted_p_values[i] = sorted_p_values[i] * (n - i)
            
            # Make adjustments monotonically decreasing
            for i in range(n-1, 0, -1):
                adjusted_sorted_p_values[i-1] = min(adjusted_sorted_p_values[i-1], 
                                                   adjusted_sorted_p_values[i])
            
            # Cap at 1.0
            adjusted_sorted_p_values = np.minimum(adjusted_sorted_p_values, 1.0)
            
            # Rearrange to original order
            adjusted_p_values = np.zeros_like(adjusted_sorted_p_values)
            adjusted_p_values[indices] = adjusted_sorted_p_values
            
        elif self.multiple_test_correction == 'benjamini-hochberg':
            # Benjamini-Hochberg procedure
            indices = np.argsort(p_values)
            sorted_p_values = p_values[indices]
            adjusted_sorted_p_values = np.zeros_like(sorted_p_values)
            
            for i in range(n-1, -1, -1):
                adjusted_sorted_p_values[i] = sorted_p_values[i] * n / (i + 1)
                if i < n-1:
                    adjusted_sorted_p_values[i] = min(adjusted_sorted_p_values[i], 
                                                     adjusted_sorted_p_values[i+1])
            
            # Cap at 1.0
            adjusted_sorted_p_values = np.minimum(adjusted_sorted_p_values, 1.0)
            
            # Rearrange to original order
            adjusted_p_values = np.zeros_like(adjusted_sorted_p_values)
            adjusted_p_values[indices] = adjusted_sorted_p_values
            
        else:
            adjusted_p_values = p_values
        
        return adjusted_p_values.tolist()
    
    def compare_strategies(self, 
                           returns1: np.ndarray, 
                           returns2: np.ndarray,
                           tests: List[str] = None) -> Dict[str, Any]:
        """
        Perform multiple statistical tests to compare strategies.
        
        Args:
            returns1: Returns of the first strategy
            returns2: Returns of the second strategy
            tests: List of tests to perform (default: all tests)
            
        Returns:
            Dictionary with test results
        """
        all_tests = ['t-test', 'sharpe', 'bootstrap-mean', 'bootstrap-sharpe']
        tests = tests or all_tests
        
        results = {}
        p_values = []
        
        # Perform selected tests
        for test in tests:
            if test == 't-test':
                results['t-test'] = self.compare_means(returns1, returns2, paired=True)
                p_values.append(results['t-test']['p_value'])
                
            elif test == 'sharpe':
                results['sharpe'] = self.compare_sharpe_ratios(returns1, returns2)
                p_values.append(results['sharpe']['p_value'])
                
            elif test == 'bootstrap-mean':
                mean_func = lambda x: np.mean(x)
                results['bootstrap-mean'] = self.bootstrap_comparison(
                    returns1, returns2, mean_func, n_iterations=1000
                )
                p_values.append(results['bootstrap-mean']['p_value'])
                
            elif test == 'bootstrap-sharpe':
                sharpe_func = lambda x: np.mean(x) / np.std(x)
                results['bootstrap-sharpe'] = self.bootstrap_comparison(
                    returns1, returns2, sharpe_func, n_iterations=1000
                )
                p_values.append(results['bootstrap-sharpe']['p_value'])
        
        # Apply multiple test correction if needed
        if self.multiple_test_correction and len(p_values) > 1:
            adjusted_p_values = self.multiple_test_correction_adjust(p_values)
            
            # Update results with adjusted p-values
            for i, test in enumerate([t for t in tests if t in results]):
                results[test]['original_p_value'] = results[test]['p_value']
                results[test]['p_value'] = adjusted_p_values[i]
                results[test]['significant'] = adjusted_p_values[i] < self.alpha
        
        # Overall conclusion
        significant_tests = [test for test in results if results[test].get('significant', False)]
        
        if len(significant_tests) > 0:
            # Count which strategy is better in significant tests
            strategy1_count = sum(1 for test in significant_tests if results[test]['better_strategy'] == 1)
            strategy2_count = sum(1 for test in significant_tests if results[test]['better_strategy'] == 2)
            
            if strategy1_count > strategy2_count:
                better_strategy = 1
            elif strategy2_count > strategy1_count:
                better_strategy = 2
            else:
                better_strategy = None  # Tie
                
            results['overall'] = {
                'significant_difference': True,
                'better_strategy': better_strategy,
                'significant_tests': significant_tests,
                'total_tests': len(tests),
                'correction_method': self.multiple_test_correction
            }
        else:
            results['overall'] = {
                'significant_difference': False,
                'better_strategy': None,
                'significant_tests': [],
                'total_tests': len(tests),
                'correction_method': self.multiple_test_correction
            }
        
        return results 