using System;
using CaeGlobals;

namespace CaeModel
{
    [Serializable]
    public class AsterMaxFrictionlessBC : BoundaryCondition
    {
        public AsterMaxFrictionlessBC(string name, string surfaceName, bool twoD)
            : base(name, surfaceName, RegionTypeEnum.SurfaceName, twoD, false, 0)
        {
        }
    }
}
