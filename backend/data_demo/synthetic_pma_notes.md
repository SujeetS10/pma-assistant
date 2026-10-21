# SYNTHETIC DEMO MATERIAL: written for smoke tests, NOT real course content

## 1. Conditional probability and Bayes' theorem

For events $A$ and $B$ with $P(B) > 0$, the conditional probability of $A$ given $B$ is
$P(A \mid B) = P(A \cap B) / P(B)$.

Bayes' theorem reverses the conditioning:

$$
P(A \mid B) = \frac{P(B \mid A)\,P(A)}{P(B)}
$$

The denominator is computed with the law of total probability over a partition $\{A_i\}$.

## 2. The geometric distribution

A geometric random variable $X$ counts the number of independent Bernoulli($p$) trials needed to get the first success. Its mass function is

$$
P(X = k) = (1-p)^{k-1}\,p, \qquad k = 1, 2, \dots
$$

The mean is $E[X] = 1/p$ and the variance is $(1-p)/p^2$.

The geometric distribution has the memoryless property: $P(X > m + n \mid X > m) = P(X > n)$.

## 3. The Poisson distribution

A Poisson($\lambda$) random variable models the count of events in a fixed interval when events occur independently at constant average rate $\lambda$.

$$
P(N = k) = \frac{e^{-\lambda}\lambda^{k}}{k!}
$$

Both the mean and the variance of a Poisson($\lambda$) variable equal $\lambda$.

## 4. Markov chains

A discrete-time Markov chain satisfies the Markov property: the next state depends only on the current state. The transition matrix $P$ has non-negative entries and each row sums to 1. A stationary distribution $\pi$ satisfies $\pi P = \pi$.
