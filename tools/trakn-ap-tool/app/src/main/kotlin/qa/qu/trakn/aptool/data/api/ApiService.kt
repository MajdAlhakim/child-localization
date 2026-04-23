package qa.qu.trakn.aptool.data.api

import okhttp3.ResponseBody
import qa.qu.trakn.aptool.data.models.ApGroupUpsertRequest
import qa.qu.trakn.aptool.data.models.GenericOkResponse
import qa.qu.trakn.aptool.data.models.GetApsResponse
import qa.qu.trakn.aptool.data.models.GridPointsResponse
import qa.qu.trakn.aptool.data.models.HealthResponse
import qa.qu.trakn.aptool.data.models.VenuesResponse
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Path

interface ApiService {

    @GET("/health")
    suspend fun health(): HealthResponse

    // Venue discovery — no auth required (read-only public list)
    @GET("/api/v1/venues")
    suspend fun getVenues(): VenuesResponse

    // Floor-plan image probe (used to confirm image exists before handing URL to Coil)
    @GET("/api/v1/floor-plans/{fpid}/image")
    suspend fun getFloorPlanImage(
        @Path("fpid") fpid: String,
    ): Response<ResponseBody>

    // Floor-plan scoped data endpoints
    @GET("/api/v1/floor-plans/{fpid}/grid")
    suspend fun getFloorPlanGrid(
        @Path("fpid") fpid: String,
        @Header("X-API-Key") apiKey: String,
    ): GridPointsResponse

    @GET("/api/v1/floor-plans/{fpid}/aps")
    suspend fun getFloorPlanAps(
        @Path("fpid") fpid: String,
        @Header("X-API-Key") apiKey: String,
    ): GetApsResponse

    @POST("/api/v1/floor-plans/{fpid}/aps")
    suspend fun postFloorPlanAps(
        @Path("fpid") fpid: String,
        @Header("X-API-Key") apiKey: String,
        @Body body: ApGroupUpsertRequest,
    ): GenericOkResponse

    @DELETE("/api/v1/floor-plans/{fpid}/aps")
    suspend fun deleteFloorPlanAps(
        @Path("fpid") fpid: String,
        @Header("X-API-Key") apiKey: String,
    ): Response<GenericOkResponse>
}
