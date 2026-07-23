from carnopy.sampling.models import Sampler

__all__ = ["Sampler", "materialize_sampler"]


def materialize_sampler(sampler: Sampler) -> list[float]:
    """Lazily import NumPy-backed sampler materialization."""

    from carnopy.sampling.generate import materialize_sampler as _materialize_sampler

    return _materialize_sampler(sampler)
